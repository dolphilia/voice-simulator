//! 二つの公開幾何APIに同じ姿勢列を与え、平均・最小セル断面積をまとめて出力する。

use std::env;
use std::error::Error;
use std::fs::File;
use std::io::{self, BufRead, BufReader, BufWriter, Write};
use std::num::NonZeroUsize;

#[cfg(fixed_upstream)]
use chimera::anatomy::human::{
    BODY_CHILD, BODY_FEMALE, BODY_MALE, HumanFrame, HumanVocalTract, NEUTRAL,
};
#[cfg(not(fixed_upstream))]
use vocal_core::anatomy::{Articulation, BodyName, Point, SagittalModel};

#[derive(Clone, Copy)]
struct Pose {
    jaw: f64,
    aperture: f64,
    tip_x: f64,
    tip_y: f64,
    protrusion: f64,
    spread: f64,
    tuck: f64,
}

#[cfg(fixed_upstream)]
fn sampler(body: usize, counts: [NonZeroUsize; 2]) -> impl FnMut(Pose, &mut Vec<f64>) {
    let mut model = HumanVocalTract::new([BODY_MALE, BODY_FEMALE, BODY_CHILD][body]);
    let mut frame = HumanFrame::default();
    let mut ph = vec![0.0; counts[0].get()];
    let mut oral = vec![0.0; counts[1].get()];
    let mut ph_min = ph.clone();
    let mut oral_min = oral.clone();
    move |input, output| {
        let mut pose = NEUTRAL;
        pose.jaw = input.jaw;
        pose.lip_ap = input.aperture;
        pose.tt_x = input.tip_x;
        pose.tt_y = input.tip_y;
        pose.lip_prot = input.protrusion;
        pose.lip_width = input.spread;
        pose.labiodental = input.tuck;
        model.compute(&pose, &mut frame);
        model.resample(
            &pose,
            &frame,
            &mut ph,
            &mut oral,
            Some(&mut ph_min),
            Some(&mut oral_min),
        );
        output.extend(ph.iter().chain(&oral).copied());
        output.extend(ph_min.iter().chain(&oral_min).copied());
    }
}

#[cfg(not(fixed_upstream))]
fn sampler(body: usize, counts: [NonZeroUsize; 2]) -> impl FnMut(Pose, &mut Vec<f64>) {
    let model =
        SagittalModel::new([BodyName::Male, BodyName::Female, BodyName::Child][body].into());
    move |input, output| {
        let mut pose = Articulation::neutral();
        pose.jaw_cm = input.jaw;
        pose.lip_aperture_cm = input.aperture;
        pose.tongue_tip_cm = Point::new(input.tip_x, input.tip_y);
        pose.lip_protrusion_cm = input.protrusion;
        pose.lip_spread = input.spread;
        pose.labiodental = input.tuck;
        let frame = model.compute(pose);
        let tract = model
            .area_profile(&frame)
            .unwrap()
            .resample(counts[0], counts[1])
            .unwrap();
        let cells = tract.pharynx.cells.iter().chain(&tract.oral.cells);
        output.extend(cells.clone().map(|cell| cell.area_cm2));
        output.extend(cells.map(|cell| cell.minimum_area_cm2));
    }
}

fn main() -> Result<(), Box<dyn Error>> {
    let args: Vec<_> = env::args().skip(1).collect();
    let [path, jaw, aperture, tip_x, tip_y, ph, oral] = args.as_slice() else {
        return Err("姿勢CSV、顎、唇の開き、舌先座標、咽頭・口腔のセル数を指定してください".into());
    };
    let (jaw, aperture) = (jaw.parse()?, aperture.parse()?);
    let (tip_x, tip_y) = (tip_x.parse()?, tip_y.parse()?);
    let counts = [ph.parse()?, oral.parse()?];
    let mut models = [0, 1, 2].map(|body| sampler(body, counts));
    let mut values = Vec::with_capacity(2 * (counts[0].get() + counts[1].get()));
    let mut output = BufWriter::new(io::stdout().lock());
    for line in BufReader::new(File::open(path)?).lines() {
        let line = line?;
        let mut fields = line.split(',');
        let body: usize = fields.next().ok_or("体型がありません")?.parse()?;
        let mut fields = fields.map(str::parse::<f64>);
        let (Some(protrusion), Some(spread), Some(tuck), None) =
            (fields.next(), fields.next(), fields.next(), fields.next())
        else {
            return Err("前突、広がり、引き込みを指定してください".into());
        };
        let pose = Pose {
            jaw,
            aperture,
            tip_x,
            tip_y,
            protrusion: protrusion?,
            spread: spread?,
            tuck: tuck?,
        };
        values.clear();
        models.get_mut(body).ok_or("体型番号が範囲外です")?(pose, &mut values);
        write!(output, "{line}")?;
        for value in &values {
            write!(output, ",{value}")?;
        }
        writeln!(output)?;
    }
    output.flush()?;
    Ok(())
}
