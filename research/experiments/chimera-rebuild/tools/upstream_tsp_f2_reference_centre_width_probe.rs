// 固定上流の costs に、保存済みの中心と評価幅の組み合わせを渡す。
#[derive(serde::Deserialize)]
struct F2CostInput {
    term: String,
    cohorts: BTreeMap<String, F2CostCohort>,
}

#[derive(serde::Deserialize)]
struct F2CostCohort {
    centres: BTreeMap<String, f64>,
    widths: BTreeMap<String, f64>,
    held: BTreeMap<String, f64>,
}

pub fn research_tsp_f2_reference_centre_width(input_path: &str) -> Result<(), String> {
    let input: F2CostInput = serde_json::from_reader(std::fs::File::open(input_path).map_err(|e| e.to_string())?)
        .map_err(|e| e.to_string())?;
    let group = group_of(&input.term);
    let mut cohorts = BTreeMap::new();
    for (name, cohort) in &input.cohorts {
        let mut cells = BTreeMap::new();
        for (centre_name, &centre) in &cohort.centres {
            for (width_name, &width) in &cohort.widths {
                let reference = Reference {
                    terms: BTreeMap::from([(input.term.clone(), (centre, width, f64::NAN))]),
                    ceps: BTreeMap::new(),
                };
                let mut observations = BTreeMap::new();
                for (voice, &log2_hz) in &cohort.held {
                    let value = Values {
                        terms: BTreeMap::from([(input.term.clone(), log2_hz)]),
                        support: BTreeMap::new(),
                        ceps: BTreeMap::new(),
                    };
                    let terms = costs(&value, &reference);
                    let (seen, cost) = terms[&input.term];
                    let (_, diagnostics) = fold(&terms);
                    observations.insert(voice, json!({
                        "log2_hz": seen, "gap_log2": (seen - centre).abs(), "cost": cost,
                        "zero": cost == 0.0, "diagnostic_cost": diagnostics.get(group),
                    }));
                }
                cells.insert(format!("{centre_name}/{width_name}"), observations);
            }
        }
        cohorts.insert(name, cells);
    }
    println!("{}", json!({
        "cohorts": cohorts, "group": group, "scored": GROUPS.contains(&group),
        "spread_floor": spread_floor(&input.term),
    }));
    Ok(())
}
