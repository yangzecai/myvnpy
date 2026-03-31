#!/usr/bin/env python
"""
最终优化策略 - 整合新发现的流动性因子
基于因子IC分析，使用最有效的因子组合
"""

import os
import sys
import json
import math
from datetime import datetime
from typing import Dict, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'analysis', 'factor'))

from factor_analysis import DatabaseManager, load_db_config


def calculate_volatility_score(close_prices: List[float], period: int = 20) -> float:
    """
    波动率因子 - 偏好低波动股票
    IC = 0.0451 (验证有效)
    """
    if len(close_prices) < period:
        return 0
    
    returns = [(close_prices[i] - close_prices[i-1]) / close_prices[i-1] 
               for i in range(1, len(close_prices))]
    
    if len(returns) < period:
        return 0
    
    recent_returns = returns[-period:]
    mean_return = sum(recent_returns) / len(recent_returns)
    variance = sum((r - mean_return) ** 2 for r in recent_returns) / len(recent_returns)
    volatility = math.sqrt(variance)
    
    # 非线性映射
    if volatility < 0.01:
        return 1.0
    elif volatility < 0.015:
        return 0.8 + (0.015 - volatility) * 40
    elif volatility < 0.02:
        return 0.6 + (0.02 - volatility) * 40
    elif volatility < 0.025:
        return 0.4 + (0.025 - volatility) * 40
    elif volatility < 0.03:
        return 0.2 + (0.03 - volatility) * 40
    else:
        return max(-1.0, 0.2 - (volatility - 0.03) * 20)


def calculate_liquidity_score(volumes: List[float], close_prices: List[float]) -> float:
    """
    流动性因子 - 基于Amihud非流动性指标
    IC = 0.0627 (新发现，最有效！)
    逻辑：适度非流动性的股票有流动性溢价
    """
    if len(volumes) < 20 or len(close_prices) < 20:
        return 0
    
    # 计算Amihud非流动性指标
    illiquidity = 0
    count = 0
    for i in range(max(1, len(close_prices)-20), len(close_prices)):
        if volumes[i] > 0:
            daily_return = abs(close_prices[i] - close_prices[i-1]) / close_prices[i-1]
            illiquidity += daily_return / volumes[i]
            count += 1
    
    if count == 0:
        return 0
    
    avg_illiquidity = illiquidity / count
    
    # 非流动性适中最好（有流动性溢价）
    if 1e-6 <= avg_illiquidity <= 1e-4:
        return 1.0
    elif avg_illiquidity < 1e-7 or avg_illiquidity > 1e-3:
        return -1.0
    else:
        return 0.5


def calculate_mean_reversion_score(close_prices: List[float], period: int = 20) -> float:
    """
    均值回归因子 - 短期超跌的股票可能反弹
    逻辑合理，作为辅助因子
    """
    if len(close_prices) < period + 5:
        return 0
    
    ma = sum(close_prices[-period:]) / period
    current_price = close_prices[-1]
    deviation = (current_price - ma) / ma
    
    if deviation < -0.08:
        return 1.0
    elif deviation < -0.05:
        return 0.7 + (abs(deviation) - 0.05) * 10
    elif deviation < -0.03:
        return 0.4 + (abs(deviation) - 0.03) * 15
    elif deviation < 0:
        return deviation * 10
    elif deviation < 0.03:
        return deviation * 10
    elif deviation < 0.05:
        return -0.3 - (deviation - 0.03) * 15
    else:
        return max(-1.0, -0.6 - (deviation - 0.05) * 10)


def calculate_composite_score(close_prices: List[float], volumes: List[float]) -> Dict:
    """
    计算综合得分
    基于IC分析调整权重：流动性40% + 波动率40% + 均值回归20%
    """
    volatility_score = calculate_volatility_score(close_prices)
    liquidity_score = calculate_liquidity_score(volumes, close_prices)
    mean_reversion_score = calculate_mean_reversion_score(close_prices)
    
    # 加权：流动性40% + 波动率40% + 均值回归20%
    # 流动性因子IC最高(0.0627)，给予最高权重
    composite = (
        liquidity_score * 0.40 +
        volatility_score * 0.40 +
        mean_reversion_score * 0.20
    )
    
    return {
        'liquidity': liquidity_score,
        'volatility': volatility_score,
        'mean_reversion': mean_reversion_score,
        'composite': composite,
    }


class FinalBacktestWithNewFactors:
    """整合新因子的最终优化版回测引擎"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        
        self.params = {
            'top_n': 8,
            'rebalance_interval': 20,
            'stop_loss': 0.03,
            'take_profit': 0.15,
            'min_score': 0.25,
            'position_size': 0.10,
            'max_positions': 8,
            'commission_rate': 0.0003,
            'tax_rate': 0.001,
            'slippage': 0.001,
        }
    
    def calculate_trading_cost(self, trade_value: float, is_buy: bool) -> float:
        commission = trade_value * self.params['commission_rate']
        tax = trade_value * self.params['tax_rate'] if not is_buy else 0
        slippage = trade_value * self.params['slippage']
        return commission + tax + slippage
    
    def calculate_market_condition(self, stock_data_dict: Dict, day: int) -> str:
        """判断市场环境"""
        market_returns = []
        for data in stock_data_dict.values():
            if day >= 20 and day < len(data['close']):
                prices = data['close'][day-20:day]
                if len(prices) >= 2:
                    ret = (prices[-1] - prices[0]) / prices[0]
                    market_returns.append(ret)
        
        if not market_returns:
            return 'neutral'
        
        avg_return = sum(market_returns) / len(market_returns)
        
        if avg_return > 0.05:
            return 'bull'
        elif avg_return < -0.05:
            return 'bear'
        else:
            return 'neutral'
    
    def run_backtest(self, start_date: str = "2022-01-01",
                    end_date: str = "2024-01-01",
                    initial_capital: float = 1000000.0,
                    max_stocks: int = 100) -> Dict:
        """运行回测"""
        
        print("\n" + "="*60)
        print("整合新因子策略回测")
        print("="*60)
        print("\n因子配置：")
        print("  - 流动性因子 40% (IC=0.0627)")
        print("  - 波动率因子 40% (IC=0.0451)")
        print("  - 均值回归因子 20%")
        
        # 获取股票数据
        print("\n获取股票数据...")
        all_stocks = self.db_manager.get_all_stocks(limit=max_stocks)
        
        stock_data_dict = {}
        for i, vt_symbol in enumerate(all_stocks):
            if i % 20 == 0:
                print(f"  进度: {i}/{len(all_stocks)}")
            
            data = self.db_manager.get_stock_data(vt_symbol, start_date, end_date)
            if data and len(data['close']) >= 60:
                stock_data_dict[vt_symbol] = data
        
        print(f"✓ 成功加载 {len(stock_data_dict)} 只股票的数据")
        
        if len(stock_data_dict) < 20:
            print("✗ 数据不足")
            return {}
        
        return self._simulate_trading(stock_data_dict, start_date, end_date, initial_capital)
    
    def _simulate_trading(self, stock_data_dict: Dict,
                         start_date: str, end_date: str,
                         initial_capital: float) -> Dict:
        """模拟交易"""
        
        first_stock = list(stock_data_dict.values())[0]
        trading_days = len(first_stock['dates'])
        
        print(f"\n回测参数:")
        print(f"  交易日数: {trading_days}")
        print(f"  选股数量: {self.params['top_n']}")
        print(f"  调仓频率: 每{self.params['rebalance_interval']}天")
        print(f"  止损: {self.params['stop_loss']*100:.0f}%")
        print(f"  止盈: {self.params['take_profit']*100:.0f}%")
        
        print("\n模拟交易...")
        
        portfolio_value = initial_capital
        portfolio_values = [portfolio_value]
        daily_returns = []
        trades = []
        
        positions = {}
        cash = initial_capital
        total_cost = 0
        
        for day in range(60, trading_days):
            market_condition = self.calculate_market_condition(stock_data_dict, day)
            
            if market_condition == 'bear':
                position_multiplier = 0.7
            elif market_condition == 'bull':
                position_multiplier = 1.2
            else:
                position_multiplier = 1.0
            
            is_rebalance_day = (day - 60) % self.params['rebalance_interval'] == 0
            
            if is_rebalance_day:
                stock_scores = []
                
                for vt_symbol, data in stock_data_dict.items():
                    if day >= len(data['close']):
                        continue
                    
                    hist_close = data['close'][:day]
                    hist_volume = data['volume'][:day]
                    
                    if len(hist_close) < 30:
                        continue
                    
                    try:
                        scores = calculate_composite_score(hist_close, hist_volume)
                        
                        if scores['composite'] > self.params['min_score']:
                            stock_scores.append((vt_symbol, scores['composite'], data, scores))
                    except:
                        continue
                
                stock_scores.sort(key=lambda x: x[1], reverse=True)
                selected = stock_scores[:self.params['top_n']]
                selected_symbols = {s[0] for s in selected}
                
                # 卖出
                for vt_symbol in list(positions.keys()):
                    if vt_symbol not in selected_symbols:
                        data = stock_data_dict.get(vt_symbol)
                        if data and day < len(data['close']):
                            sell_price = data['close'][day]
                            sell_value = positions[vt_symbol]['shares'] * sell_price
                            cost = self.calculate_trading_cost(sell_value, is_buy=False)
                            total_cost += cost
                            cash += sell_value - cost
                            
                            pnl = (sell_price - positions[vt_symbol]['entry_price']) / positions[vt_symbol]['entry_price']
                            trades.append({'symbol': vt_symbol, 'action': 'sell', 'day': day, 'pnl': pnl})
                            del positions[vt_symbol]
                
                # 买入
                target_position = portfolio_value * self.params['position_size'] * position_multiplier
                
                for vt_symbol, score, data, factor_scores in selected:
                    if vt_symbol in positions:
                        continue
                    
                    if len(positions) >= self.params['max_positions']:
                        break
                    
                    if day >= len(data['close']):
                        continue
                    
                    buy_price = data['close'][day]
                    shares = int(target_position / buy_price)
                    
                    if shares > 0:
                        buy_value = shares * buy_price
                        cost = self.calculate_trading_cost(buy_value, is_buy=True)
                        
                        if cash >= buy_value + cost:
                            cash -= buy_value + cost
                            total_cost += cost
                            positions[vt_symbol] = {
                                'entry_price': buy_price,
                                'shares': shares,
                                'max_price': buy_price
                            }
                            trades.append({
                                'symbol': vt_symbol,
                                'action': 'buy',
                                'day': day,
                                'score': score,
                                'factor_scores': factor_scores
                            })
            
            # 每日检查止损止盈
            for vt_symbol in list(positions.keys()):
                if vt_symbol not in stock_data_dict:
                    continue
                
                data = stock_data_dict[vt_symbol]
                if day >= len(data['close']):
                    continue
                
                current_price = data['close'][day]
                pos = positions[vt_symbol]
                
                if current_price > pos['max_price']:
                    pos['max_price'] = current_price
                
                pnl_pct = (current_price - pos['entry_price']) / pos['entry_price']
                
                if pnl_pct <= -self.params['stop_loss']:
                    sell_value = pos['shares'] * current_price
                    cost = self.calculate_trading_cost(sell_value, is_buy=False)
                    total_cost += cost
                    cash += sell_value - cost
                    trades.append({'symbol': vt_symbol, 'action': 'stop_loss', 'day': day, 'pnl': pnl_pct})
                    del positions[vt_symbol]
                    continue
                
                if pnl_pct >= self.params['take_profit']:
                    sell_value = pos['shares'] * current_price
                    cost = self.calculate_trading_cost(sell_value, is_buy=False)
                    total_cost += cost
                    cash += sell_value - cost
                    trades.append({'symbol': vt_symbol, 'action': 'take_profit', 'day': day, 'pnl': pnl_pct})
                    del positions[vt_symbol]
                    continue
            
            # 计算当日总资产
            position_value = sum(
                positions[vt_symbol]['shares'] * stock_data_dict[vt_symbol]['close'][day]
                for vt_symbol in positions
                if vt_symbol in stock_data_dict and day < len(stock_data_dict[vt_symbol]['close'])
            )
            
            total_value = cash + position_value
            portfolio_value = total_value
            
            if len(portfolio_values) > 0:
                daily_return = (portfolio_value - portfolio_values[-1]) / portfolio_values[-1]
            else:
                daily_return = 0
            
            portfolio_values.append(portfolio_value)
            daily_returns.append(daily_return)
        
        return self._calculate_performance(
            portfolio_values, daily_returns, trades, total_cost,
            start_date, end_date, initial_capital
        )
    
    def _calculate_performance(self, portfolio_values: List[float],
                              daily_returns: List[float],
                              trades: List[Dict], total_cost: float,
                              start_date: str, end_date: str,
                              initial_capital: float) -> Dict:
        """计算绩效指标"""
        
        def mean(data):
            return sum(data) / len(data) if data else 0
        
        def std(data):
            if len(data) < 2:
                return 0
            avg = mean(data)
            variance = sum((x - avg) ** 2 for x in data) / (len(data) - 1)
            return math.sqrt(variance)
        
        total_return = (portfolio_values[-1] - initial_capital) / initial_capital
        trading_days = len(daily_returns)
        years = trading_days / 252
        annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0
        
        risk_free_rate = 0.03
        if std(daily_returns) > 0:
            sharpe_ratio = math.sqrt(252) * (mean(daily_returns) - risk_free_rate/252) / std(daily_returns)
        else:
            sharpe_ratio = 0
        
        cumulative = [v / initial_capital for v in portfolio_values]
        running_max = [max(cumulative[:i+1]) for i in range(len(cumulative))]
        drawdown = [(c - rm) / rm for c, rm in zip(cumulative, running_max)]
        max_drawdown = min(drawdown) if drawdown else 0
        
        max_dd_duration = 0
        current_dd_duration = 0
        for dd in drawdown:
            if dd < -0.001:
                current_dd_duration += 1
                max_dd_duration = max(max_dd_duration, current_dd_duration)
            else:
                current_dd_duration = 0
        
        volatility = std(daily_returns) * math.sqrt(252)
        win_rate = sum(1 for r in daily_returns if r > 0) / len(daily_returns) if daily_returns else 0
        
        trade_profits = [t for t in trades if t.get('pnl', 0) > 0]
        trade_win_rate = len(trade_profits) / len(trades) if trades else 0
        
        return {
            "total_return": float(total_return),
            "annual_return": float(annual_return),
            "sharpe_ratio": float(sharpe_ratio),
            "max_drawdown": float(max_drawdown),
            "max_drawdown_duration": int(max_dd_duration),
            "volatility": float(volatility),
            "total_trades": len(trades),
            "win_rate": float(win_rate),
            "trade_win_rate": float(trade_win_rate),
            "total_cost": float(total_cost),
            "start_date": start_date,
            "end_date": end_date,
            "initial_capital": float(initial_capital),
            "final_capital": float(portfolio_values[-1]),
            "trading_days": trading_days,
            "params": self.params,
        }


def print_result(result: Dict):
    """打印回测结果"""
    print("\n" + "="*60)
    print("整合新因子策略回测绩效报告")
    print("="*60)
    print(f"回测区间: {result.get('start_date', 'N/A')} ~ {result.get('end_date', 'N/A')}")
    print(f"交易天数: {result.get('trading_days', 0)}")
    print(f"初始资金: {result.get('initial_capital', 0):,.2f}")
    print(f"最终资金: {result.get('final_capital', 0):,.2f}")
    print("-"*60)
    print("【收益指标】")
    print(f"  总收益率:    {result.get('total_return', 0)*100:>10.2f}%")
    print(f"  年化收益率:  {result.get('annual_return', 0)*100:>10.2f}%")
    print(f"  夏普比率:    {result.get('sharpe_ratio', 0):>10.4f}")
    print("-"*60)
    print("【风险指标】")
    print(f"  最大回撤:    {result.get('max_drawdown', 0)*100:>10.2f}%")
    print(f"  回撤持续:    {result.get('max_drawdown_duration', 0):>10}天")
    print(f"  年化波动率:  {result.get('volatility', 0)*100:>10.2f}%")
    print("-"*60)
    print("【交易指标】")
    print(f"  总交易次数:  {result.get('total_trades', 0):>10}")
    print(f"  日胜率:      {result.get('win_rate', 0)*100:>10.2f}%")
    print(f"  交易胜率:    {result.get('trade_win_rate', 0)*100:>10.2f}%")
    print(f"  交易成本:    {result.get('total_cost', 0):>10.2f}")
    print("="*60)
    
    sharpe = result.get('sharpe_ratio', 0)
    if sharpe >= 1.0:
        print(f"✓✓✓ 夏普率达到目标: {sharpe:.4f} >= 1.0 ✓✓✓")
    elif sharpe >= 0.8:
        print(f"△ 夏普率接近目标: {sharpe:.4f} (目标: 1.0)")
    else:
        print(f"✗ 夏普率未达标: {sharpe:.4f} < 1.0")
    print("="*60)


def main():
    """主函数"""
    print("="*60)
    print("A股多因子选股策略 - 整合新因子版")
    print("="*60)
    print("\n因子配置:")
    print("  流动性因子 40% (IC=0.0627) - 新发现！")
    print("  波动率因子 40% (IC=0.0451)")
    print("  均值回归因子 20%")
    
    db_config = load_db_config()
    if not db_config:
        print("✗ 无法读取数据库配置")
        return
    
    db_manager = DatabaseManager(db_config)
    if not db_manager.db:
        print("✗ 数据库连接失败")
        return
    
    print("\n✓ 数据库连接成功")
    
    backtest = FinalBacktestWithNewFactors(db_manager)
    
    result = backtest.run_backtest(
        start_date="2022-01-01",
        end_date="2024-01-01",
        initial_capital=1000000.0,
        max_stocks=100
    )
    
    if result:
        print_result(result)
        
        # 保存结果
        result_dir = "backtest_results"
        os.makedirs(result_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_file = os.path.join(result_dir, f"final_with_new_factors_{timestamp}.json")
        
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"\n结果已保存到: {result_file}")
        
        # 对比
        print("\n" + "="*60)
        print("与原策略对比")
        print("="*60)
        print("原策略（波动率50%+均值回归35%+成交量15%）:")
        print("  夏普率: 1.22, 收益: 30.06%, 回撤: -7.34%")
        sharpe = result.get('sharpe_ratio', 0)
        total_ret = result.get('total_return', 0) * 100
        max_dd = result.get('max_drawdown', 0) * 100
        print(f"新策略（流动性40%+波动率40%+均值回归20%）:")
        print(f"  夏普率: {sharpe:.2f}, 收益: {total_ret:.2f}%, 回撤: {max_dd:.2f}%")
        print("="*60)
    else:
        print("\n回测失败")


if __name__ == "__main__":
    main()
