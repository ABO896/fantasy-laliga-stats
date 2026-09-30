import type { HitBucket, RecordBucket, TrackRecordResponse } from "../api-client/market-model";

/** "75.0% (3/4)" — a hit rate never travels without its sample size. */
export function formatRate(bucket: HitBucket | undefined): string {
  if (!bucket || bucket.hitRate === null) return "—";
  return `${(bucket.hitRate * 100).toFixed(1)}% (${bucket.hits}/${bucket.scored})`;
}

/** Which record a tier's hit rate is quoted from: live calls once any are
 * scored, otherwise the retroactive backtest — and the label always says
 * which, so a backtest can never pass for a live record. */
export function tierRecord(record: TrackRecordResponse | undefined): {
  label: "live" | "backtest";
  bucket: RecordBucket | undefined;
} {
  if (record && record.ours.live.scored > 0) return { label: "live", bucket: record.ours.live };
  return { label: "backtest", bucket: record?.ours.retroactive };
}
