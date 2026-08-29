import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { BacktestAssumptions } from "@/domain";
import { METRICS } from "@/lib/i18n/vi";

type ExecutionAssumptionsProps = {
  assumptions: BacktestAssumptions;
};

export const ExecutionAssumptions = ({ assumptions }: ExecutionAssumptionsProps) => (
  <Card className="border-amber-200">
    <CardHeader>
      <CardTitle>Giả định khớp lệnh</CardTitle>
      <p className="text-sm text-slate-500">
        Cách mô phỏng khớp lệnh, chi phí và thoát lệnh — theo quy tắc kiểm toán của engine.
      </p>
    </CardHeader>
    <CardContent>
      <dl className="grid gap-4 sm:grid-cols-2">
        {[
          ["Thời điểm vào lệnh", assumptions.candleTiming],
          ["Khớp lệnh", assumptions.execution],
          ["Spread", assumptions.spread],
          ["Trượt giá", assumptions.slippage],
          [METRICS.commission, assumptions.commission],
          [METRICS.swap, assumptions.swap],
          ["Chi phí thoát lệnh", assumptions.exitCosts],
          ["Kích thước vị thế", assumptions.positionSizing],
          ["Giới hạn vị thế", assumptions.positionLimit],
          ["Quy tắc thoát cùng nến", assumptions.sameBarExitRule],
          ["Hết dữ liệu", assumptions.endOfData],
        ].map(([label, value]) => (
          <div key={String(label)} className="rounded-lg border border-slate-200 p-3">
            <dt className="text-xs uppercase text-slate-500">{label}</dt>
            <dd className="mt-1 text-sm leading-relaxed text-slate-800">{value}</dd>
          </div>
        ))}
      </dl>
    </CardContent>
  </Card>
);
