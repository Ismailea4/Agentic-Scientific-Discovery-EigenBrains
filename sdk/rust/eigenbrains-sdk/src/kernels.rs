//! Dependency-free numerical kernels for high-volume telemetry paths.
//!
//! The entropy kernel mirrors `discolab.telemetry.population_entropy`
//! operation by operation (bin index `trunc((x - lo) / (hi - lo) * bins)`
//! clipped to the box, natural logarithms, NumPy's pairwise summation), so
//! results agree with the authoritative Python to within floating-point
//! rounding of the logarithm. Parity is asserted against Python outputs, never
//! assumed.

/// NumPy's pairwise summation (`pairwise_sum` in `loops_utils.h`): 8 partial
/// sums for blocks up to 128 elements, recursive halving above that.
pub fn pairwise_sum(values: &[f64]) -> f64 {
    let n = values.len();
    if n < 8 {
        let mut res = 0.0;
        for &v in values {
            res += v;
        }
        res
    } else if n <= 128 {
        let mut r = [0.0f64; 8];
        r.copy_from_slice(&values[..8]);
        let mut i = 8;
        while i < n - (n % 8) {
            for (j, acc) in r.iter_mut().enumerate() {
                *acc += values[i + j];
            }
            i += 8;
        }
        let mut res = ((r[0] + r[1]) + (r[2] + r[3])) + ((r[4] + r[5]) + (r[6] + r[7]));
        while i < n {
            res += values[i];
            i += 1;
        }
        res
    } else {
        let mut half = n / 2;
        half -= half % 8;
        pairwise_sum(&values[..half]) + pairwise_sum(&values[half..])
    }
}

/// Mean fixed-bin Shannon entropy across columns of a row-major
/// `rows x cols` population, normalized to [0, 1].
pub fn normalized_histogram_entropy(
    points: &[f64],
    rows: usize,
    cols: usize,
    lower: f64,
    upper: f64,
    bins: usize,
) -> Result<f64, &'static str> {
    if rows == 0 || cols == 0 || points.len() != rows * cols {
        return Err("invalid matrix shape");
    }
    if bins < 2 || !lower.is_finite() || !upper.is_finite() || upper <= lower {
        return Err("invalid entropy bounds");
    }
    let span = upper - lower;
    let nbins = bins as f64;
    let n = rows as f64;
    let log_bins = nbins.ln();
    let mut counts = vec![0usize; bins];
    let mut terms = vec![0.0f64; bins];
    let mut per_column = Vec::with_capacity(cols);
    for col in 0..cols {
        counts.fill(0);
        for row in 0..rows {
            let x = points[row * cols + col];
            if !x.is_finite() {
                return Err("non-finite sample");
            }
            let raw = ((x - lower) / span * nbins) as i64; // truncation toward zero, as astype(int)
            counts[raw.clamp(0, bins as i64 - 1) as usize] += 1;
        }
        for (term, &count) in terms.iter_mut().zip(&counts) {
            let p = count as f64 / n;
            *term = if count > 0 { p * p.ln() } else { 0.0 };
        }
        per_column.push(-pairwise_sum(&terms) / log_bins);
    }
    Ok(pairwise_sum(&per_column) / cols as f64)
}

/// Entropy of every population in a row-major `(snapshots, rows, cols)` block.
pub fn population_entropy_batch(
    data: &[f64],
    snapshots: usize,
    rows: usize,
    cols: usize,
    lower: f64,
    upper: f64,
    bins: usize,
) -> Result<Vec<f64>, &'static str> {
    let size = rows * cols;
    if data.len() != snapshots * size {
        return Err("invalid batch shape");
    }
    data.chunks_exact(size.max(1))
        .take(snapshots)
        .map(|chunk| normalized_histogram_entropy(chunk, rows, cols, lower, upper, bins))
        .collect()
}

/// Mean of the worst `tail_probability` fraction (upper tail).
pub fn cvar_upper(values: &[f64], tail_probability: f64) -> Result<f64, &'static str> {
    if values.is_empty() || !(0.0 < tail_probability && tail_probability <= 1.0) {
        return Err("invalid CVaR input");
    }
    let mut sorted = values.to_vec();
    if sorted.iter().any(|x| !x.is_finite()) {
        return Err("non-finite sample");
    }
    sorted.sort_by(|a, b| b.total_cmp(a));
    let n = ((sorted.len() as f64 * tail_probability).ceil() as usize).max(1);
    Ok(sorted[..n].iter().sum::<f64>() / n as f64)
}

/// Wilson score interval for a binomial proportion.
pub fn wilson_interval(
    successes: u64,
    trials: u64,
    z: f64,
) -> Result<(f64, f64, f64), &'static str> {
    if trials == 0 || successes > trials || !z.is_finite() || z <= 0.0 {
        return Err("invalid Wilson input");
    }
    let n = trials as f64;
    let p = successes as f64 / n;
    let z2 = z * z;
    let center = (p + z2 / (2.0 * n)) / (1.0 + z2 / n);
    let half = z * ((p * (1.0 - p) / n + z2 / (4.0 * n * n)).sqrt()) / (1.0 + z2 / n);
    Ok((p, (center - half).max(0.0), (center + half).min(1.0)))
}

/// Order statistics of timing samples (linear interpolation, like NumPy's default).
pub fn quantile(sorted: &[f64], q: f64) -> f64 {
    if sorted.is_empty() {
        return f64::NAN;
    }
    let pos = q.clamp(0.0, 1.0) * (sorted.len() - 1) as f64;
    let lo = pos.floor() as usize;
    let hi = pos.ceil() as usize;
    sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo as f64)
}
