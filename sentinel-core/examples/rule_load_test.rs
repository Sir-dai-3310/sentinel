use sentinel_core::sigma::SigmaEngine;

fn main() {
    let engine = SigmaEngine::new("../rules".to_string()).expect("Failed to load rules");

    let count = engine.rule_count();
    println!("✅ Successfully loaded {} rules", count);

    if count >= 100 {
        println!("✅ PASS: {} rules >= 100", count);
    } else {
        println!("❌ FAIL: {} rules < 100", count);
        std::process::exit(1);
    }
}
