extern crate cubeb_backend;
extern crate cubeb_coreaudio;
extern crate mach2;

use cubeb_backend::ffi;
use mach2::mach_time::{mach_timebase_info, mach_timebase_info_data_t};
use std::convert::TryInto;
use std::ffi::CStr;
use std::io::{self, Read};
use std::os::raw::{c_int, c_long, c_void};
use std::path::Path;
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::time::{Duration, Instant};
use std::{env, fs, mem, ptr, slice, thread};

struct Probe {
    overrun_index: usize,
    delay: Duration,
    callbacks: AtomicUsize,
    frames: AtomicUsize,
    stream_error: AtomicBool,
    marker_period: Option<Vec<f32>>,
}

unsafe extern "C" fn render(
    _: *mut ffi::cubeb_stream,
    user: *mut c_void,
    _: *const c_void,
    output: *mut c_void,
    frames: c_long,
) -> c_long {
    if frames <= 0 || output.is_null() {
        return ffi::CUBEB_ERROR.into();
    }
    let probe = &*user.cast::<Probe>();
    let index = probe.callbacks.load(Ordering::Relaxed);
    if index == probe.overrun_index {
        let started = Instant::now();
        while started.elapsed() < probe.delay {
            std::hint::spin_loop();
        }
    }
    let offset = probe.frames.fetch_add(frames as usize, Ordering::Relaxed);
    let samples = slice::from_raw_parts_mut(output.cast::<[f32; 2]>(), frames as usize);
    if let Some(period) = &probe.marker_period {
        for (frame, stereo) in samples.iter_mut().enumerate() {
            let value = period[(offset + frame) % period.len()];
            *stereo = [value, -value];
        }
    } else {
        for (frame, stereo) in samples.iter_mut().enumerate() {
            let marker = (((offset + frame) * 421 + 173) % 65521) as i32 - 32760;
            let value = marker as f32 / 8388608.0;
            *stereo = [value, -value];
        }
    }
    probe.callbacks.fetch_add(1, Ordering::Release);
    frames
}

unsafe extern "C" fn state(_: *mut ffi::cubeb_stream, user: *mut c_void, state: ffi::cubeb_state) {
    if state == ffi::CUBEB_STATE_ERROR {
        let probe = &*user.cast::<Probe>();
        probe.stream_error.store(true, Ordering::Release);
    }
}

fn check(name: &str, status: c_int) -> Result<(), String> {
    if status == ffi::CUBEB_OK {
        Ok(())
    } else {
        Err(format!("{}: {}", name, status))
    }
}

unsafe fn run(
    probe: &Probe,
    rate: u32,
    latency: u32,
    callbacks: usize,
    ready: Option<&Path>,
) -> Result<(), String> {
    let mut context = ptr::null_mut();
    let name = b"CHIMERA cubeb output probe\0".as_ptr().cast();
    check(
        "audiounit_rust_init",
        cubeb_coreaudio::audiounit_rust_init(&mut context, name),
    )?;
    let mut stream = ptr::null_mut();
    let mut params = ffi::cubeb_stream_params {
        format: ffi::CUBEB_SAMPLE_FLOAT32NE,
        rate,
        channels: 2,
        layout: ffi::CUBEB_LAYOUT_STEREO,
        prefs: ffi::CUBEB_STREAM_PREF_NONE,
        input_params: ffi::CUBEB_INPUT_PROCESSING_PARAM_NONE,
    };
    let result = (|| {
        check(
            "cubeb_stream_init",
            ffi::cubeb_stream_init(
                context,
                &mut stream,
                name,
                ptr::null(),
                ptr::null_mut(),
                ptr::null(),
                &mut params,
                latency,
                Some(render),
                Some(state),
                ptr::from_ref(probe).cast_mut().cast(),
            ),
        )?;
        let mut timebase: mach_timebase_info_data_t = mem::zeroed();
        check("mach_timebase_info", mach_timebase_info(&mut timebase))?;
        let backend = CStr::from_ptr(ffi::cubeb_get_backend_id(context)).to_string_lossy();
        if let Some(ready) = ready {
            fs::write(ready, []).map_err(|error| error.to_string())?;
            let mut released = [0];
            io::stdin()
                .read_exact(&mut released)
                .map_err(|error| error.to_string())?;
            if released != [1] {
                return Err("出力開始の合図が一致しません".into());
            }
        }
        check("cubeb_stream_start", ffi::cubeb_stream_start(stream))?;
        let started = Instant::now();
        while probe.callbacks.load(Ordering::Acquire) < callbacks
            && !probe.stream_error.load(Ordering::Acquire)
            && started.elapsed() < Duration::from_secs(5)
        {
            thread::sleep(Duration::from_millis(5));
        }
        check("cubeb_stream_stop", ffi::cubeb_stream_stop(stream))?;
        let observed = probe.callbacks.load(Ordering::Acquire);
        if observed < callbacks || probe.stream_error.load(Ordering::Acquire) {
            return Err(format!(
                "コールバック {} 件。要求は {} 件",
                observed, callbacks
            ));
        }
        println!(
            "{{\"backend\":\"{}\",\"callbacks\":{},\"timebase_numer\":{},\"timebase_denom\":{}}}",
            backend, observed, timebase.numer, timebase.denom
        );
        Ok(())
    })();
    if !stream.is_null() {
        ffi::cubeb_stream_destroy(stream);
    }
    ffi::cubeb_destroy(context);
    result
}

fn load_marker(path: &Path) -> Result<Vec<f32>, String> {
    let bytes = fs::read(path).map_err(|error| error.to_string())?;
    if bytes.is_empty() || bytes.len() % 4 != 0 {
        return Err("試験信号は空でないFloat32のPCMを指定してください".into());
    }
    let marker: Vec<_> = bytes
        .chunks_exact(4)
        .map(|row| f32::from_le_bytes(row.try_into().unwrap()))
        .collect();
    if marker
        .iter()
        .any(|value| !value.is_finite() || value.abs() > 1.0)
    {
        return Err("試験信号に有限のPCM範囲を超える値があります".into());
    }
    Ok(marker)
}

fn main() -> Result<(), String> {
    let args: Vec<_> = env::args().skip(1).collect();
    if args.len() != 5 && args.len() != 7 {
        return Err("レート、要求フレーム数、遅延を入れる番号、遅延µs、観測件数を指定してください。タップを同時採取する場合は続けてモノラルPCMと準備通知のパスを指定してください".into());
    }
    let parse = |index: usize| args[index].parse::<u32>().map_err(|e| e.to_string());
    let probe = Probe {
        overrun_index: parse(2)? as usize,
        delay: Duration::from_micros(u64::from(parse(3)?)),
        callbacks: AtomicUsize::new(0),
        frames: AtomicUsize::new(0),
        stream_error: AtomicBool::new(false),
        marker_period: args
            .get(5)
            .map(|path| load_marker(Path::new(path)))
            .transpose()?,
    };
    let ready = args.get(6).map(Path::new);
    unsafe { run(&probe, parse(0)?, parse(1)?, parse(4)? as usize, ready) }
}
