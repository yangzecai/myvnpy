#!/usr/bin/env python
"""
改进版策略回测
基于因子分析和成本分析的结论进行重构

改进点：
1. 移除失效的动量因子和技术因子
2. 只使用有效的波动率因子（低波动策略）
3. 添加新的反转因子（均值回归）
4. 大幅降低调仓频率（每20天）
5. 提高选股门槛
"""

import os
import sys
import json
import math
from datetime import datetime
from typing import Dict, List, Optional
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from factor_analysis import DatabaseManager, load_db_config


def calculate_volatility_score(close_prices: List[float], period: int = 20) -> float:
    """
    计算波动率得分
    偏好低波动股票
    """
    if len(close_prices) < period:
        return 0
    
    # 计算收益率
    returns = [(close_prices[i] - close_prices[i-1]) / close_prices[i-1] 
               for i in range(1, len(close_prices))]
    
    # 计算标准差
    if len(returns) < period:
        return 0
    
    recent_returns = returns[-period:]
    mean_return = sum(recent_returns) / len(recent_returns)
    variance = sum((r - mean_return) ** 2 for r in recent_returns) / len(recent_returns)
    volatility = math.sqrt(variance)
    
    # 波动率越低得分越高
    # 假设正常日波动在0.01-0.03之间
    if volatility < 0.015:
        return 1.0
    elif volatility > 0.03:
        return -1.0
    else:
        return 1.0 - (volatility - 0.015) / 0.015


def calculate_mean_reversion_score(close_prices: List[float], period: int = 20) -> float:
    """
    计算均值回归得分
    短期超跌的股票可能反弹
    """
    if len(close_prices) < period + 5:
        return 0
    
    # 计算均线
    ma = sum(close_prices[-period:]) / period
    current_price = close_prices[-1]
    
    # 计算偏离度
    deviation = (current_price - ma) / ma
    
    # 价格低于均线越多，得分越高（均值回归预期）
    if deviation < -0.05:  # 超跌5%以上
        return min(1.0, abs(deviation) * 10)
    elif deviation > 0.05:  # 超买
        return max(-1.0, -deviation * 10)
    else:
        return -deviation * 10  # 线性映射


def calculate_volume_score(volumes: List[float]) -> float:
    """
    计算成交量得分
    偏好温和放量的股票
    """
    if len(volumes) < 20:
        return 0
    
    current_vol = volumes[-1]
    avg_vol = sum(volumes[-20:]) / 20
    
    if avg_vol == 0:
        return 0
    
    ratio = current_vol / avg_vol
    
    # 温和放量为正面信号
    if 1.0 <= ratio <= 2.0:
        return (ratio - 1.0) * 2 - 0.5
    elif ratio > 2.0:
        return 0.5 - (ratio - 2.0) * 0.5
    else:
        return ratio - 1.0


def calculate_composite_score(close_prices: List[float], volumes: List[float]) -> Dict:
    """
    计算综合得分
    基于分析结果，只使用有效因子
    """
    volatility_score = calculate_volatility_score(close_prices)
    mean_reversion_score = calculate_mean_reversion_score(close_prices)
    volume_score = calculate_volume_score(volumes)
    
    # 加权：波动率40% + 均值回归40% + 成交量20%
    composite = (
        volatility_score * 0.4 +
        mean_reversion_score * 0.4 +
        volume_score * 0.2
    )
    
    return {
        'volatility': volatility_score,
        'mean_reversion': mean_reversion_score,
        'volume': volume_score,
        'composite': composite,
    }


class ImprovedBacktest:
    """改进版回测引擎"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        
        # 优化后的参数
        self.params = {
            'top_n': 10,              # 选股数量
            'rebalance_interval': 20, # 调仓频率（每20天）
            'stop_loss': 0.05,        # 止损5%
            'take_profit': 0.10,      # 止盈10%
            'min_score': 0.2,         # 选股门槛
            'position_size': 0.08,    # 单股仓位8%
            'max_positions': 10,      # 最大持仓
            'commission_rate': 0.0003, # 佣金万3
            'tax_rate': 0.001,        # 印花税千1
            'slippage': 0.001,        # 滑点0.1%
        }
    
    def calculate_trading_cost(self, trade_value: float, is_buy: bool) -> float:
        """计算交易成本"""
        commission = trade_value * self.params['commission_rate']
        tax = trade_value * self.params['tax_rate'] if not is_buy else 0
        slippage = trade_value * self.params['slippage']
        return commission + tax + slippage
    
    def run_backtest(self, start_date: str = "2022-01-01",
                    end_date: str = "2024-01-01",
                    initial_capital: float = 1000000.0,
                    max_stocks: int = 100) -> Dict:
        """运行改进版回测"""
        
        print("\n" + "="*60)
        print("改进版策略回测")
        print("="*60)
        
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
        print(f"  选股门槛: {self.params['min_score']}")
        
        print("\n模拟交易...")
        
        portfolio_value = initial_capital
        portfolio_values = [portfolio_value]
        daily_returns = []
        trades = []
        
        positions = {}
        cash = initial_capital
        total_cost = 0
        
        for day in range(60, trading_days):
            # 只在调仓日进行选股和调仓
            is_rebalance_day = (day - 60) % self.params['rebalance_interval'] == 0
            
            if is_rebalance_day:
                # 对每只股票评分
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
                            stock_scores.append((vt_symbol, scores['composite'], data))
                    except:
                        continue
                
                # 排序并选择前N只
                stock_scores.sort(key=lambda x: x[1], reverse=True)
                selected = stock_scores[:self.params['top_n']]
                selected_symbols = {s[0] for s in selected}
                
                # 卖出不在选股列表的股票
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
                
                # 买入新选中的股票
                target_position = portfolio_value * self.params['position_size']
                
                for vt_symbol, score, data in selected:
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
                                'price': buy_price,
                                'shares': shares
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
                
                # 更新最高价
                if current_price > pos['max_price']:
                    pos['max_price'] = current_price
                
                pnl_pct = (current_price - pos['entry_price']) / pos['entry_price']
                
                # 止损
                if pnl_pct <= -self.params['stop_loss']:
                    sell_value = pos['shares'] * current_price
                    cost = self.calculate_trading_cost(sell_value, is_buy=False)
                    total_cost += cost
                    cash += sell_value - cost
                    trades.append({'symbol': vt_symbol, 'action': 'stop_loss', 'day': day, 'pnl': pnl_pct})
                    del positions[vt_symbol]
                    continue
                
                # 止盈
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
            
            # 计算日收益率
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
        
        # 夏普比率
        risk_free_rate = 0.03
        if std(daily_returns) > 0:
            sharpe_ratio = math.sqrt(252) * (mean(daily_returns) - risk_free_rate/252) / std(daily_returns)
        else:
            sharpe_ratio = 0
        
        # 最大回撤
        cumulative = [v / initial_capital for v in portfolio_values]
        running_max = [max(cumulative[:i+1]) for i in range(len(cumulative))]
        drawdown = [(c - rm) / rm for c, rm in zip(cumulative, running_max)]
        max_drawdown = min(drawdown) if drawdown else 0
        
        # 回撤持续期
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
        
        # 交易胜率
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
    print("改进版策略回测绩效报告")
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
        print(f"✓ 夏普率达到目标: {sharpe:.4f} >= 1.0")
    elif sharpe >= 0.5:
        print(f"△ 夏普率有所改善: {sharpe:.4f} (目标: 1.0)")
    else:
        print(f"✗ 夏普率未达标: {sharpe:.4f} < 1.0")
    print("="*60)


def main():
    """主函数"""
    print("="*60)
    print("A股多因子选股策略 - 改进版回测")
    print("="*60)
    print("\n改进内容:")
    print("1. 移除失效的动量因子和技术因子")
    print("2. 只使用有效的波动率因子（低波动策略）")
    print("3. 添加均值回归因子")
    print("4. 降低调仓频率至每20天")
    print("5. 提高选股门槛至0.2")
    
    db_config = load_db_config()
    if not db_config:
        print("✗ 无法读取数据库配置")
        return
    
    db_manager = DatabaseManager(db_config)
    if not db_manager.db:
        print("✗ 数据库连接失败")
        return
    
    backtest = ImprovedBacktest(db_manager)
    
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
        result_file = os.path.join(result_dir, f"improved_strategy_{timestamp}.json")
        
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"\n结果已保存到: {result_file}")
    else:
        print("\n回测失败")


if __name__ == "__main__":
    main()
