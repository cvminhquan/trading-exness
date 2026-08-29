import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { BacktestClassification } from "@/domain";
import { UI } from "@/lib/i18n/vi";

type BacktestInterpretationProps = {
  classification: BacktestClassification | null;
};

export const BacktestInterpretation = ({ classification }: BacktestInterpretationProps) => (
  <Card className="border-slate-700/60">
    <CardHeader>
      <CardTitle>Diễn giải &amp; hạn chế</CardTitle>
    </CardHeader>
    <CardContent className="space-y-4 text-sm leading-relaxed text-slate-400">
      <p>
        Kết quả Backtest là{" "}
        <strong className="font-medium text-slate-300">mô phỏng lịch sử</strong>. Chúng không đảm
        bảo lợi nhuận trong tương lai. Giao dịch thực tế có thể khác do độ trễ, spread biến động,
        trượt giá, từ chối lệnh, thanh khoản và cách khớp lệnh riêng của broker.
      </p>
      <p>
        Giả định khớp lệnh (spread, trượt giá, phí hoa hồng, phí qua đêm, quy tắc cùng nến) ảnh
        hưởng đáng kể đến kết quả ròng. Luôn xem xét PnL gộp so với PnL ròng và mục giả định khớp
        lệnh trước khi rút kết luận.
      </p>
      {classification ? (
        <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-4">
          <p className="font-medium text-slate-200">{classification.classification}</p>
          <ul className="mt-3 list-disc space-y-2 pl-5">
            {classification.rationale.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-slate-500">{UI.researchOnly}.</p>
        </div>
      ) : null}
    </CardContent>
  </Card>
);
