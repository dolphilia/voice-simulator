//! マニフェストに記載されたファイルをストリームで読み、サイズとSHA-256を照合する。

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    error::Error,
    fs::File,
    io::{self, BufReader, Read},
    path::{Component, Path, PathBuf},
};

#[derive(Deserialize)]
pub(super) struct Manifest {
    pub run_id: String,
    status: Option<String>,
    pub upstream_revision: String,
    #[serde(default)]
    outputs: Vec<Artifact>,
    #[serde(default)]
    cases: Vec<RecordedCase>,
}

#[derive(Deserialize)]
struct RecordedCase {
    id: String,
    status: String,
    outputs: Vec<Artifact>,
}

pub(super) struct RegisteredArtifact<'a> {
    pub entry: &'a Artifact,
    pub status: &'a str,
    pub case_id: Option<&'a str>,
}

#[derive(Clone, Deserialize, Serialize)]
pub(super) struct Artifact {
    pub path: PathBuf,
    pub bytes: u64,
    pub sha256: String,
}

pub(super) struct Run {
    root: PathBuf,
    pub manifest: Manifest,
}

impl Run {
    pub fn load(path: &Path) -> Result<Self, Box<dyn Error>> {
        let manifest = if path.is_dir() {
            path.join("manifest.json")
        } else {
            path.to_path_buf()
        };
        let file = File::open(&manifest)
            .map_err(|e| format!("{} を開けません ({e})", manifest.display()))?;
        let record = serde_json::from_reader(BufReader::new(file))
            .map_err(|e| format!("{} を読めません ({e})", manifest.display()))?;
        let root = manifest
            .parent()
            .ok_or("マニフェストの親ディレクトリがありません")?;
        Ok(Self {
            root: root.to_path_buf(),
            manifest: record,
        })
    }

    pub fn artifact(&self, path: &Path) -> Result<RegisteredArtifact<'_>, Box<dyn Error>> {
        if path.as_os_str().is_empty()
            || !path
                .components()
                .all(|part| matches!(part, Component::Normal(_)))
        {
            return Err(format!("実行内の相対パスを指定してください ({})", path.display()).into());
        }
        let top = self
            .manifest
            .outputs
            .iter()
            .map(|entry| (entry, self.manifest.status.as_deref(), None));
        let nested = self.manifest.cases.iter().flat_map(|case| {
            case.outputs
                .iter()
                .map(|entry| (entry, Some(case.status.as_str()), Some(case.id.as_str())))
        });
        let mut outputs = top.chain(nested).filter(|(entry, _, _)| entry.path == path);
        let (entry, status, case_id) = outputs.next().ok_or_else(|| {
            format!(
                "{} のマニフェストに {} がありません",
                self.manifest.run_id,
                path.display()
            )
        })?;
        if outputs.next().is_some() {
            return Err(format!(
                "マニフェストの成果パスが重複しています ({})",
                path.display()
            )
            .into());
        }
        let status = status.ok_or("マニフェストに成果の実行状態がありません")?;
        Ok(RegisteredArtifact {
            entry,
            status,
            case_id,
        })
    }

    pub fn open(&self, artifact: &Artifact) -> Result<CheckedFile, Box<dyn Error>> {
        let path = self.root.join(&artifact.path);
        let file =
            File::open(&path).map_err(|e| format!("{} を開けません ({e})", path.display()))?;
        let metadata = file.metadata()?;
        if !metadata.is_file() || metadata.len() != artifact.bytes {
            return Err(format!(
                "{} のファイル種別またはサイズが記録と異なります",
                path.display()
            )
            .into());
        }
        Ok(CheckedFile {
            file,
            path,
            expected: artifact.clone(),
            hash: Sha256::new(),
            bytes_read: 0,
        })
    }
}

pub(super) struct CheckedFile {
    file: File,
    path: PathBuf,
    expected: Artifact,
    hash: Sha256,
    bytes_read: u64,
}

impl Read for CheckedFile {
    fn read(&mut self, buffer: &mut [u8]) -> io::Result<usize> {
        let size = self.file.read(buffer)?;
        self.hash.update(&buffer[..size]);
        self.bytes_read += size as u64;
        Ok(size)
    }
}

impl CheckedFile {
    pub fn finish(mut self) -> Result<(), Box<dyn Error>> {
        // 区間外もハッシュには含めるので、選択区間に関係なく全体を照合できる。
        io::copy(&mut self, &mut io::sink())?;
        if self.bytes_read != self.expected.bytes
            || !format!("{:x}", self.hash.finalize()).eq_ignore_ascii_case(&self.expected.sha256)
        {
            return Err(format!(
                "{} のサイズまたはSHA-256が記録と異なります",
                self.path.display()
            )
            .into());
        }
        Ok(())
    }
}

#[derive(Clone, Copy, Eq, PartialEq, Serialize)]
#[serde(rename_all = "lowercase")]
pub(super) enum WaveFormat {
    Pcm16,
    Float32,
}

impl WaveFormat {
    fn sample_bytes(self) -> u16 {
        match self {
            Self::Pcm16 => 2,
            Self::Float32 => 4,
        }
    }
}

pub(super) struct Wave {
    source: BufReader<CheckedFile>,
    pub format: WaveFormat,
    pub rate: u32,
    pub frames: u64,
}

impl Wave {
    pub fn open(run: &Run, artifact: &Artifact) -> Result<Self, Box<dyn Error>> {
        Self::read(run.open(artifact)?, artifact.bytes)
            .map_err(|error| format!("{}: {error}", artifact.path.display()).into())
    }

    fn read(file: CheckedFile, file_size: u64) -> Result<Self, Box<dyn Error>> {
        let mut source = BufReader::new(file);
        let mut head = [0; 12];
        source.read_exact(&mut head)?;
        let riff_size = u64::from(u32::from_le_bytes(head[4..8].try_into()?));
        if &head[..4] != b"RIFF" || &head[8..] != b"WAVE" || riff_size + 8 != file_size {
            return Err("RIFF/WAVEのヘッダーまたはサイズが不正です".into());
        }
        let mut remaining = file_size - 12;
        let mut format_info = None;
        while remaining >= 8 {
            let mut chunk = [0; 8];
            source.read_exact(&mut chunk)?;
            let size = u64::from(u32::from_le_bytes(chunk[4..].try_into()?));
            let padded = size + size % 2;
            remaining -= 8;
            if padded > remaining {
                return Err("WAVのチャンクがファイルの長さを超えています".into());
            }
            let mut consumed = 0;
            match &chunk[..4] {
                b"fmt " => {
                    if size < 16 || format_info.is_some() {
                        return Err("WAVのfmtチャンクが不正です".into());
                    }
                    let mut format = [0; 16];
                    source.read_exact(&mut format)?;
                    let sample_rate = u32::from_le_bytes(format[4..8].try_into()?);
                    let byte_rate = u32::from_le_bytes(format[8..12].try_into()?);
                    let tag = u16::from_le_bytes(format[0..2].try_into()?);
                    let bits = u16::from_le_bytes(format[14..16].try_into()?);
                    let specification = match (tag, bits) {
                        (1, 16) => WaveFormat::Pcm16,
                        (3, 32) => WaveFormat::Float32,
                        _ => return Err("WAVはPCM16またはIEEE float32を指定してください".into()),
                    };
                    let stride = specification.sample_bytes();
                    if format[2..4] != [1, 0]
                        || format[12..14] != stride.to_le_bytes()
                        || sample_rate == 0
                        || sample_rate.checked_mul(u32::from(stride)) != Some(byte_rate)
                    {
                        return Err("モノラルWAVのチャンネル数またはサンプル情報が不正です".into());
                    }
                    format_info = Some((specification, sample_rate));
                    consumed = 16;
                }
                b"data" => {
                    let (format, rate) =
                        format_info.ok_or("WAVのfmtチャンクがPCMデータより前にありません")?;
                    let stride = u64::from(format.sample_bytes());
                    if !size.is_multiple_of(stride) {
                        return Err("WAVのPCMデータ長が不正です".into());
                    }
                    return Ok(Self {
                        source,
                        format,
                        rate,
                        frames: size / stride,
                    });
                }
                _ => {}
            }
            let skip = padded - consumed;
            if io::copy(&mut (&mut source).take(skip), &mut io::sink())? != skip {
                return Err("WAVのチャンクの末尾が欠けています".into());
            }
            remaining -= padded;
        }
        Err("WAVにPCMデータがありません".into())
    }

    pub fn sample(&mut self) -> Result<f32, Box<dyn Error>> {
        let sample = match self.format {
            WaveFormat::Pcm16 => {
                let mut bytes = [0; 2];
                self.source.read_exact(&mut bytes)?;
                // 固定上流のWAV入力と同じスケール。16ビットの全整数をf32で正確に表せる。
                f32::from(i16::from_le_bytes(bytes)) / 32768.0
            }
            WaveFormat::Float32 => {
                let mut bytes = [0; 4];
                self.source.read_exact(&mut bytes)?;
                f32::from_le_bytes(bytes)
            }
        };
        if !sample.is_finite() {
            return Err("WAVのPCMに非有限値があります".into());
        }
        Ok(sample)
    }

    pub fn finish(self) -> Result<(), Box<dyn Error>> {
        self.source.into_inner().finish()
    }
}

#[derive(Clone, Copy, Default, Deserialize)]
#[serde(rename_all = "snake_case")]
pub(super) enum Coordinate {
    #[default]
    InternalSample,
    Frame,
}

impl Coordinate {
    fn name(self) -> &'static str {
        match self {
            Self::InternalSample => "internal_sample",
            Self::Frame => "frame",
        }
    }

    pub fn at(self, frame: u64, end_sample: u64) -> u64 {
        match self {
            Self::InternalSample => end_sample,
            Self::Frame => frame,
        }
    }
}

pub(super) struct Trace {
    source: csv::Reader<CheckedFile>,
    path: PathBuf,
    index: usize,
    fields: Vec<usize>,
    row: csv::StringRecord,
    last: Option<u64>,
}

impl Trace {
    pub fn open(
        run: &Run,
        artifact: &Artifact,
        axis: Coordinate,
        fields: &[String],
    ) -> Result<Self, Box<dyn Error>> {
        let mut source = csv::Reader::from_reader(run.open(artifact)?);
        let header = source.headers()?;
        let column = |name: &str| {
            let mut hits = header
                .iter()
                .enumerate()
                .filter(|(_, field)| *field == name);
            match (hits.next(), hits.next()) {
                (Some((index, _)), None) => Ok(index),
                _ => Err(format!(
                    "{} に一意の列 {} がありません",
                    artifact.path.display(),
                    name
                )),
            }
        };
        let index = column(axis.name())?;
        let fields = fields
            .iter()
            .map(|name| column(name))
            .collect::<Result<_, _>>()?;
        Ok(Self {
            source,
            path: artifact.path.clone(),
            index,
            fields,
            row: csv::StringRecord::new(),
            last: None,
        })
    }

    pub fn values_at(&mut self, position: u64, values: &mut [f64]) -> Result<(), Box<dyn Error>> {
        while self.source.read_record(&mut self.row)? {
            let coordinate = self.row[self.index]
                .parse::<u64>()
                .map_err(|e| format!("{} の観測座標が不正です ({e})", self.path.display()))?;
            if self.last.is_some_and(|last| coordinate <= last) {
                return Err(format!(
                    "{} の観測座標が昇順ではありません ({coordinate})",
                    self.path.display()
                )
                .into());
            }
            self.last = Some(coordinate);
            if coordinate < position {
                continue;
            }
            if coordinate > position {
                break;
            }
            for (value, &column) in values.iter_mut().zip(&self.fields) {
                *value = self.row[column].parse::<f64>().map_err(|e| {
                    format!(
                        "{} の座標 {position} に不正な数値があります ({e})",
                        self.path.display()
                    )
                })?;
                if !value.is_finite() {
                    return Err(format!(
                        "{} の座標 {position} に非有限値があります",
                        self.path.display()
                    )
                    .into());
                }
            }
            return Ok(());
        }
        Err(format!("{} の観測座標 {position} がありません", self.path.display()).into())
    }

    pub fn finish(self) -> Result<(), Box<dyn Error>> {
        self.source.into_inner().finish()
    }
}
