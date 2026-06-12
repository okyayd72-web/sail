/**
 * SAIL Future Scholarship Engine
 * ================================
 * STATUS: DORMANT — NOT CONNECTED TO PRODUCTION
 *
 * TODO: Activate UTR-based scholarship engine after beta testing.
 * TODO: Populate lineup UTR data for all schools before enabling this feature.
 * TODO: Replace current scholarship estimation in tennis_routes.py
 *       once roster UTR data is available for enough schools.
 *
 * This file contains the complete infrastructure for a future
 * UTR-based scholarship estimation system. It is intentionally
 * disconnected from all production code, UI, and matching logic.
 *
 * DO NOT import or call these functions in production until
 * roster UTR data has been collected and validated.
 */

'use strict';

// ─────────────────────────────────────────────
// DIVISION FALLBACK DEFAULTS
// Used when a school has no roster UTR data yet.
// TODO: Replace per-school with real data after beta.
// ─────────────────────────────────────────────
const DIVISION_DEFAULTS = {
  "NCAA I": {
    men:   { top: 13.5, bottom: 11.0 },
    women: { top: 11.5, bottom:  9.0 }
  },
  "NCAA II": {
    men:   { top: 12.5, bottom: 10.0 },
    women: { top: 10.5, bottom:  8.0 }
  },
  "NCAA III": {
    men:   { top: 11.5, bottom:  8.5 },
    women: { top:  9.5, bottom:  7.0 }
  },
  "NAIA": {
    men:   { top: 12.0, bottom:  9.5 },
    women: { top: 10.0, bottom:  7.5 }
  },
  "JUCO": {
    men:   { top: 11.0, bottom:  8.0 },
    women: { top:  9.0, bottom:  6.5 }
  }
};

// ─────────────────────────────────────────────
// SCHOLARSHIP POTENTIAL LABELS
// Describes the estimated scholarship outcome
// in plain language for the UI.
// TODO: Connect to school card UI after activation.
// ─────────────────────────────────────────────
const SCHOLARSHIP_LABELS = {
  FULL:        { label: 'Full Scholarship Potential',    color: '#00c9a7', minPercentile: 0.85 },
  HIGH:        { label: 'High Scholarship Potential',    color: '#22c55e', minPercentile: 0.65 },
  MODERATE:    { label: 'Moderate Scholarship Potential',color: '#e8b84b', minPercentile: 0.40 },
  LOW:         { label: 'Partial Aid Possible',          color: '#8fa0b8', minPercentile: 0.20 },
  UNLIKELY:    { label: 'Athletic Aid Unlikely',         color: '#ef4444', minPercentile: 0.00 },
};

// ─────────────────────────────────────────────
// CORE FUNCTIONS
// ─────────────────────────────────────────────

/**
 * Clamps a value between min and max.
 * @param {number} value
 * @param {number} min
 * @param {number} max
 * @returns {number}
 */
function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

/**
 * Calculates where a player's UTR sits within a team's lineup range.
 * Returns a percentile between 0 (bottom of roster) and 1 (top of roster).
 *
 * Formula: (playerUTR - bottomLineupUTR) / (topLineupUTR - bottomLineupUTR)
 *
 * @param {number} playerUTR - The athlete's UTR rating
 * @param {number} topLineupUTR - The team's top player UTR
 * @param {number} bottomLineupUTR - The team's bottom player UTR
 * @returns {number} Percentile between 0 and 1
 */
function calculatePercentile(playerUTR, topLineupUTR, bottomLineupUTR) {
  if (topLineupUTR === bottomLineupUTR) return 0.5; // Avoid division by zero
  const raw = (playerUTR - bottomLineupUTR) / (topLineupUTR - bottomLineupUTR);
  return clamp(raw, 0, 1);
}

/**
 * Estimates scholarship amount based on percentile position.
 * Higher percentile = closer to full scholarship.
 *
 * Formula: averageScholarship * (0.6 + 0.8 * percentile)
 * At percentile 0: 60% of average scholarship
 * At percentile 1: 140% of average scholarship (full + above average)
 *
 * @param {number} averageScholarship - School's average scholarship amount
 * @param {number} percentile - Player's percentile (0-1)
 * @returns {number} Estimated scholarship amount
 */
function calculateEstimatedScholarship(averageScholarship, percentile) {
  if (!averageScholarship) return 0;
  return averageScholarship * (0.6 + 0.8 * percentile);
}

/**
 * Calculates low and high scholarship estimate range (±10%).
 *
 * @param {number} estimatedScholarship
 * @returns {{ low: number, high: number }}
 */
function calculateScholarshipRange(estimatedScholarship) {
  return {
    low:  Math.round(estimatedScholarship * 0.9),
    high: Math.round(estimatedScholarship * 1.1),
  };
}

/**
 * Gets the lineup UTR range for a school.
 * Uses real school data if available, falls back to division defaults.
 *
 * @param {Object} school - School record from tennis_schools.json
 * @param {string} gender - 'male' or 'female'
 * @returns {{ top: number, bottom: number }}
 */
function getLineupUTRRange(school, gender) {
  const genderKey = gender === 'male' ? 'men' : 'women';
  const topField    = gender === 'male' ? 'top_lineup_utr_men'    : 'top_lineup_utr_women';
  const bottomField = gender === 'male' ? 'bottom_lineup_utr_men' : 'bottom_lineup_utr_women';

  // Use real data if available
  if (school[topField] && school[bottomField]) {
    return {
      top:    school[topField],
      bottom: school[bottomField],
    };
  }

  // Fall back to division defaults
  const division = school.division || 'NCAA II';
  const defaults = DIVISION_DEFAULTS[division] || DIVISION_DEFAULTS['NCAA II'];
  return defaults[genderKey];
}

/**
 * Gets the scholarship potential label based on percentile.
 *
 * @param {number} percentile - 0 to 1
 * @returns {Object} Label object from SCHOLARSHIP_LABELS
 */
function getScholarshipLabel(percentile) {
  if (percentile >= SCHOLARSHIP_LABELS.FULL.minPercentile)     return SCHOLARSHIP_LABELS.FULL;
  if (percentile >= SCHOLARSHIP_LABELS.HIGH.minPercentile)     return SCHOLARSHIP_LABELS.HIGH;
  if (percentile >= SCHOLARSHIP_LABELS.MODERATE.minPercentile) return SCHOLARSHIP_LABELS.MODERATE;
  if (percentile >= SCHOLARSHIP_LABELS.LOW.minPercentile)      return SCHOLARSHIP_LABELS.LOW;
  return SCHOLARSHIP_LABELS.UNLIKELY;
}

/**
 * MASTER FUNCTION — Full scholarship estimate for one school.
 * Combines all calculations into a single result object.
 *
 * TODO: Call this function from tennis_routes.py (Python equivalent)
 *       after beta testing when roster UTR data is ready.
 *
 * @param {number} playerUTR
 * @param {string} gender - 'male' or 'female'
 * @param {Object} school - School record from tennis_schools.json
 * @returns {ScholarshipEstimate}
 */
function estimateScholarshipFull(playerUTR, gender, school) {
  // NCAA III gives no athletic scholarships
  if (school.division === 'NCAA III') {
    return {
      percentile:          null,
      estimatedAmount:     0,
      lowEstimate:         0,
      highEstimate:        0,
      label:               { label: 'No Athletic Scholarships (D3)', color: '#4d6278' },
      usingFallback:       false,
      avgTeamUTR:          null,
    };
  }

  const genderKey      = gender === 'male' ? 'men' : 'women';
  const avgScholarship = gender === 'male'
    ? school.mens_scholarship
    : school.womens_scholarship;

  const lineupRange   = getLineupUTRRange(school, gender);
  const usingFallback = !(gender === 'male' ? school.top_lineup_utr_men : school.top_lineup_utr_women);

  const percentile         = calculatePercentile(playerUTR, lineupRange.top, lineupRange.bottom);
  const estimatedAmount    = calculateEstimatedScholarship(avgScholarship, percentile);
  const { low, high }      = calculateScholarshipRange(estimatedAmount);
  const label              = getScholarshipLabel(percentile);

  const avgTeamUTR = gender === 'male'
    ? school.avg_team_utr_men
    : school.avg_team_utr_women;

  return {
    percentile:       Math.round(percentile * 100),   // 0-100 for display
    estimatedAmount:  Math.round(estimatedAmount),
    lowEstimate:      low,
    highEstimate:     high,
    label,
    usingFallback,
    avgTeamUTR,
  };
}

// ─────────────────────────────────────────────
// EXPORTS (for future Node.js / bundler use)
// TODO: Import these in production tennis_routes equivalent
//       after beta testing is complete.
// ─────────────────────────────────────────────
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    estimateScholarshipFull,
    calculatePercentile,
    calculateEstimatedScholarship,
    calculateScholarshipRange,
    getLineupUTRRange,
    getScholarshipLabel,
    DIVISION_DEFAULTS,
    SCHOLARSHIP_LABELS,
  };
}