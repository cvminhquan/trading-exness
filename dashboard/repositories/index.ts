export type { TradingRepository } from "./trading-repository";
export { MockTradingRepository } from "./mock-trading-repository";
export { ApiTradingRepository } from "./api-trading-repository";
export {
  createTradingRepository,
  getTradingRepository,
  resetTradingRepository,
  setTradingRepository,
} from "./create-trading-repository";

import { getTradingRepository } from "./create-trading-repository";

/** Singleton repository — mock hoặc API tùy NEXT_PUBLIC_DATA_SOURCE. */
export const tradingRepository = getTradingRepository();
