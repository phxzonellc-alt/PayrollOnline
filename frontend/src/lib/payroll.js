export function calcGross(r1, r2, sr, s1, o1, d1, s2, o2, d2, srh) {
  if ((s1 + o1 + d1) === 0) {
    return (r2 * s2) + (r2 * 1.5 * o2) + (r2 * 2 * d2) + (sr * srh);
  }
  return (r1 * s1) + (r1 * 1.5 * o1) + (r1 * 2 * d1) + (sr * srh);
}

export const $f = (v) =>
  '$' + (v || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const DAYS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];

export const HOUR_FIELDS = ['st_r1', 'ot_r1', 'dt_r1', 'st_r2', 'ot_r2', 'dt_r2', 'sr_hours'];

export function sumField(arr, field) {
  return arr.reduce((s, e) => s + (e[field] || 0), 0);
}
