#!/usr/bin/env python
"""
策略参数优化
通过网格搜索找到最优参数组合
"""

import os
import sys
import json
import math
from datetime import datetime
from typing import Dict, List, Tuple
from itertools import product

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from run_improved_strategy import (
    calculate_composite_score, 
    DatabaseManager, 
    load_db_config
)


class OptimizedBacktest:
    """参数可配置的回测引擎"""
    
    def __init__(self, db_manager: DatabaseManager, params: Dict):
        self.db_manager = db_manager
        self.params = params
    
    def calculate_trading_cost(self, trade_value: float, is_buy: bool) -> float:
        commission = trade_value * self.params['commission_rate']
        tax = trade_value * self.params['tax_rate'] if not is_buy else 0
        slippage = trade_value * self.params['slippage']
        return commission + tax + slippage
    
    def run_backtest(self, stock_data_dict: Dict, 
                    start_date: str, end_date: str,
                    initial_capital: float = 1000000.0) -> Dict:
        """运行回测"""
        
        first_stock = list(stock_data_dict.values())[0]
        trading_days = len(first_stock['dates'])
        
        portfolio_value = initial_capital
        portfolio_values = [portfolio_value]
        daily_returns = []
        trades = []
        
        positions = {}
        cash = initial_capital
        total_cost = 0
        
        for day in range(60, trading_days):
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
                            stock_scores.append((vt_symbol, scores['composite'], data))
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
                            trades.append({'pnl': pnl})
                            del positions[vt_symbol]
                
                # 买入
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
                
                # 止损
                if pnl_pct <= -self.params['stop_loss']:
                    sell_value = pos['shares'] * current_price
                    cost = self.calculate_trading_cost(sell_value, is_buy=False)
                    total_cost += cost
                    cash += sell_value - cost
                    trades.append({'pnl': pnl_pct})
                    del positions[vt_symbol]
                    continue
                
                # 止盈
                if pnl_pct >= self.params['take_profit']:
                    sell_value = pos['shares'] * current_price
                    cost = self.calculate_trading_cost(sell_value, is_buy=False)
                    total_cost += cost
                    cash += sell_value - cost
                    trades.append({'pnl': pnl_pct})
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
        
        volatility = std(daily_returns) * math.sqrt(252)
        win_rate = sum(1 for r in daily_returns if r > 0) / len(daily_returns) if daily_returns else 0
        
        trade_profits = [t for t in trades if t.get('pnl', 0) > 0]
        trade_win_rate = len(trade_profits) / len(trades) if trades else 0
        
        return {
            "total_return": float(total_return),
            "annual_return": float(annual_return),
            "sharpe_ratio": float(sharpe_ratio),
            "max_drawdown": float(max_drawdown),
            "volatility": float(volatility),
            "total_trades": len(trades),
            "win_rate": float(win_rate),
            "trade_win_rate": float(trade_win_rate),
            "total_cost": float(total_cost),
            "params": self.params,
        }


def grid_search(db_manager: DatabaseManager, stock_data_dict: Dict) -> Tuple[Dict, float]:
    """
    网格搜索最优参数
    """
    print("\n" + "="*60)
    print("策略参数优化 - 网格搜索")
    print("="*60)
    
    # 参数搜索空间
    param_grid = {
        'rebalance_interval': [10, 15, 20, 25, 30],
        'stop_loss': [0.03, 0.05, 0.07, 0.10],
        'take_profit': [0.08, 0.10, 0.15, 0.20],
        'min_score': [0.1, 0.15, 0.2, 0.25],
        'position_size': [0.06, 0.08, 0.10],
    }
    
    # 固定参数
    base_params = {
        'top_n': 10,
        'max_positions': 10,
        'commission_rate': 0.0003,
        'tax_rate': 0.001,
        'slippage': 0.001,
    }
    
    best_sharpe = -float('inf')
    best_params = None
    best_result = None
    
    # 生成所有参数组合
    param_names = list(param_grid.keys())
    param_values = list(param_grid.values())
    total_combinations = 1
    for v in param_values:
        total_combinations *= len(v)
    
    print(f"\n搜索空间: {total_combinations} 种参数组合")
    print("-"*60)
    
    results = []
    
    for i, values in enumerate(product(*param_values)):
        params = base_params.copy()
        for name, value in zip(param_names, values):
            params[name] = value
        
        backtest = OptimizedBacktest(db_manager, params)
        result = backtest.run_backtest(
            stock_data_dict,
            start_date="2022-01-01",
            end_date="2024-01-01",
            initial_capital=1000000.0
        )
        
        sharpe = result['sharpe_ratio']
        results.append((params, result))
        
        if sharpe > best_sharpe:
            best_sharpe = sharpe
            best_params = params.copy()
            best_result = result
            print(f"[{i+1}/{total_combinations}] 新最优夏普: {sharpe:.4f}")
            print(f"  参数: 调仓{params['rebalance_interval']}天, 止损{params['stop_loss']:.0%}, 止盈{params['take_profit']:.0%}, 门槛{params['min_score']}")
        
        if (i + 1) % 50 == 0:
            print(f"  进度: {i+1}/{total_combinations}, 当前最优: {best_sharpe:.4f}")
    
    return best_params, best_sharpe, best_result, results


def main():
    """主函数"""
    print("="*60)
    print("A股多因子选股策略 - 参数优化")
    print("="*60)
    
    db_config = load_db_config()
    if not db_config:
        print("✗ 无法读取数据库配置")
        return
    
    db_manager = DatabaseManager(db_config)
    if not db_manager.db:
        print("✗ 数据库连接失败")
        return
    
    print("✓ 数据库连接成功")
    
    # 加载数据
    print("\n加载股票数据...")
    all_stocks = db_manager.get_all_stocks(limit=100)
    
    stock_data_dict = {}
    for i, vt_symbol in enumerate(all_stocks):
        if i % 20 == 0:
            print(f"  进度: {i}/{len(all_stocks)}")
        
        data = db_manager.get_stock_data(vt_symbol, "2022-01-01", "2024-01-01")
        if data and len(data['close']) >= 60:
            stock_data_dict[vt_symbol] = data
    
    print(f"✓ 成功加载 {len(stock_data_dict)} 只股票的数据")
    
    if len(stock_data_dict) < 20:
        print("✗ 数据不足")
        return
    
    # 网格搜索
    best_params, best_sharpe, best_result, all_results = grid_search(db_manager, stock_data_dict)
    
    # 打印最优结果
    print("\n" + "="*60)
    print("最优参数组合")
    print("="*60)
    print(f"夏普比率: {best_sharpe:.4f}")
    print(f"\n参数设置:")
    for key, value in best_params.items():
        if key in ['stop_loss', 'take_profit']:
            print(f"  {key}: {value:.0%}")
        else:
            print(f"  {key}: {value}")
    
    print(f"\n绩效指标:")
    print(f"  总收益率: {best_result['total_return']*100:.2f}%")
    print(f"  年化收益率: {best_result['annual_return']*100:.2f}%")
    print(f"  最大回撤: {best_result['max_drawdown']*100:.2f}%")
    print(f"  年化波动率: {best_result['volatility']*100:.2f}%")
    print(f"  交易胜率: {best_result['trade_win_rate']*100:.2f}%")
    
    # 保存结果
    result_dir = "backtest_results"
    os.makedirs(result_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_file = os.path.join(result_dir, f"optimization_results_{timestamp}.json")
    
    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump({
            'best_params': best_params,
            'best_result': best_result,
            'all_results': [(p, r) for p, r in all_results[:20]]  # 只保存前20个
        }, f, indent=2, ensure_ascii=False)
    
    print(f"\n结果已保存到: {result_file}")
    
    if best_sharpe >= 1.0:
        print("\n✓ 夏普率达到目标 1.0!")
    else:
        print(f"\n△ 最优夏普率: {best_sharpe:.4f}, 距离目标 1.0 还有 {1.0 - best_sharpe:.4f}")


if __name__ == "__main__":
    main()
