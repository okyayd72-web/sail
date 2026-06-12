/**
 * SAIL Future Scholarship Engine — TypeScript Types
 * ==================================================
 * STATUS: DORMANT — NOT CONNECTED TO PRODUCTION
 *
 * TODO: Activate after beta testing and roster UTR data collection.
 * These types define the data structures for the future
 * UTR-based scholarship estimation system.
 */

// ─────────────────────────────────────────────
// SCHOOL RECORD — Updated Schema
// The new optional fields added for Phase 2.
// Current fields remain unchanged.
// ─────────────────────────────────────────────
export interface SchoolRecord {
  // Existing fields (currently active)
  school:              string;
  city:                string | null;
  state:               string | null;
  division:            string;
  mens_scholarship:    number | null;
  womens_scholarship:  number | null;
  avg_sat:             number | null;
  avg_act:             number | null;
  instate_tuition:     number | null;
  outstate_tuition:    number | null;
  coach:               string | null;
  phone:               string | null;
  email:               string | null;
  usnews_ranking:      number | null;

  // Phase 2 fields — all null until populated after beta
  // TODO: Populate these from tennisrecruiting.net and UTR database
  avg_team_utr_men:        number | null;
  avg_team_utr_women:      number | null;
  top_lineup_utr_men:      number | null;
  bottom_lineup_utr_men:   number | null;
  top_lineup_utr_women:    number | null;
  bottom_lineup_utr_women: number | null;
}

// ─────────────────────────────────────────────
// SCHOLARSHIP ESTIMATE — Full Result Object
// Returned by estimateScholarshipFull()
// TODO: Display this in SchoolCard component after activation
// ─────────────────────────────────────────────
export interface ScholarshipEstimate {
  /** Player's percentile within team roster (0-100) */
  percentile:       number | null;

  /** Point estimate of scholarship amount in USD */
  estimatedAmount:  number;

  /** Low end of scholarship range (estimatedAmount * 0.9) */
  lowEstimate:      number;

  /** High end of scholarship range (estimatedAmount * 1.1) */
  highEstimate:     number;

  /** Human-readable label and color for UI display */
  label:            ScholarshipLabel;

  /** True if school-specific UTR data was unavailable, division defaults used */
  usingFallback:    boolean;

  /** Average team UTR for context display */
  avgTeamUTR:       number | null;
}

// ─────────────────────────────────────────────
// SCHOLARSHIP LABEL — UI Display Object
// ─────────────────────────────────────────────
export interface ScholarshipLabel {
  label:        string;
  color:        string;
  minPercentile: number;
}

// ─────────────────────────────────────────────
// LINEUP UTR RANGE — Per school, per gender
// ─────────────────────────────────────────────
export interface LineupUTRRange {
  top:    number;   // Top ranked player's UTR
  bottom: number;   // Bottom ranked player's UTR
}

// ─────────────────────────────────────────────
// DIVISION DEFAULTS — Fallback when no school data
// ─────────────────────────────────────────────
export interface DivisionDefaults {
  men:   LineupUTRRange;
  women: LineupUTRRange;
}

export type DivisionDefaultsMap = {
  [division: string]: DivisionDefaults;
};

// ─────────────────────────────────────────────
// FUTURE UI PROPS — For school card component
// TODO: Pass ScholarshipEstimate to SchoolCard after activation
// ─────────────────────────────────────────────
export interface SchoolCardProps {
  school:              SchoolRecord;
  playerUTR:           number;
  gender:              'male' | 'female';

  // TODO: Replace current estimate display with this
  scholarshipEstimate?: ScholarshipEstimate;

  // Current active fields (keep until Phase 2 activated)
  currentEstimateLow?:  number | null;
  currentEstimateHigh?: number | null;
}

// ─────────────────────────────────────────────
// FUTURE API RESPONSE — /api/tennis/schools
// TODO: Add scholarshipEstimate to each school
//       in the API response after activation
// ─────────────────────────────────────────────
export interface TennisSchoolsResponse {
  schools:      SchoolRecord[];
  total:        number;
  locked_count: number;
  is_premium:   boolean;
  beta_mode:    boolean;

  // TODO: Add after Phase 2 activation
  // estimation_method?: 'utr_based' | 'historical_average';
}