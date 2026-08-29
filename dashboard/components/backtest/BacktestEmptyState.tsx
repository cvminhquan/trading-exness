import { EmptyState } from "@/components/shared/States";

export const BacktestEmptyState = () => (
  <EmptyState
    title="Chưa có báo cáo Backtest nào"
    description="Chạy mô phỏng lịch sử từ trading engine và nhập báo cáo kết quả vào đây. Dữ liệu hiệu suất sẽ hiển thị khi có lần chạy baseline hoàn tất."
  />
);
