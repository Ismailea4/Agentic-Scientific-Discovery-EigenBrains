use eigenbrains_sdk::kernels::normalized_histogram_entropy;
use std::time::Instant;

fn main() {
    let rows = 100_000;
    let cols = 10;
    let points: Vec<f64> = (0..rows * cols).map(|i| (i % 1000) as f64 / 100.0 - 5.0).collect();
    let started = Instant::now();
    let entropy = normalized_histogram_entropy(&points, rows, cols, -5.0, 5.0, 20).unwrap();
    println!("entropy={entropy:.6} elapsed={:?}", started.elapsed());
}
