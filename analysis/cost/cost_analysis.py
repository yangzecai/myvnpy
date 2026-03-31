#!/usr/bin/env python
"""
交易成本敏感性分析
分析交易成本对策略收益的影响
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


class CostAnalyzer:
    """交易成本分析器"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        
        # 交易成本参数
        self.commission_rate = 0.0003  # 佣金万3
        self.tax_rate = 0.001  # 印花税千1（卖出）
        self.slippage = 0.001  # 滑点0.1%
    
    def calculate_trading_cost(self, trade_value: float, is_buy: bool) -> float:
        """
        计算单次交易成本
        
        :param trade_value: 交易金额
        :param is_buy: 是否买入
        :return: 交易成本
        """
        # 佣金
        commission = trade_value * self.commission_rate
        
        # 印花税（卖出时收取）
        tax = trade_value * self.tax_rate if not is_buy else 0
        
        # 滑点
        slippage_cost = trade_value * self.slippage
        
        return commission + tax + slippage_cost
    
    def analyze_rebalance_frequency(self, stock_data_dict: Dict,
                                   rebalance_intervals: List[int] = [1, 5, 10, 20]) -> Dict:
        """
        分析不同调仓频率对收益的影响
        
        :param rebalance_intervals: 调仓间隔天数列表
        :return: 各频率下的回测结果
        """
        print("\n分析不同调仓频率的影响...")
        
        results = {}
        
        for interval in rebalance_intervals:
            print(f"\n测试调仓频率: 每{interval}天")
            result = self._backtest_with_frequency(stock_data_dict, interval)
            results[f"interval_{interval}"] = result
            
            print(f"  总收益: {result['total_return']*100:.2f}%")
            print(f"  交易成本: {result['total_cost']:.2f}")
            print(f"  交易次数: {result['trade_count']}")
        
        return results
    
    def _backtest_with_frequency(self, stock_data_dict: Dict, 
                                 rebalance_interval: int) -> Dict:
        """使用指定调仓频率进行回测"""
        
        # 获取交易日列表
        first_stock = list(stock_data_dict.values())[0]
        trading_days = len(first_stock['dates'])
        
        # 简化回测：假设每天选前10只股票，等权重持有
        portfolio_value = 1000000.0
        total_cost = 0.0
        trade_count = 0
        
        # 模拟持仓
        positions = {}  # {vt_symbol: {'shares': int, 'cost': float}}
        cash = portfolio_value
        
        for day in range(60, trading_days, rebalance_interval):
            # 计算每只股票过去20天收益（简化选股逻辑）
            stock_returns = []
            
            for vt_symbol, data in stock_data_dict.items():
                if day >= len(data['close']):
                    continue
                
                hist_close = data['close'][:day]
                if len(hist_close) >= 20:
                    ret = (hist_close[-1] - hist_close[-20]) / hist_close[-20]
                    stock_returns.append((vt_symbol, ret, data))
            
            # 选前10只
            stock_returns.sort(key=lambda x: x[1], reverse=True)
            selected = stock_returns[:10]
            selected_symbols = {s[0] for s in selected}
            
            # 卖出不在选股列表的股票
            for vt_symbol in list(positions.keys()):
                if vt_symbol not in selected_symbols:
                    data = stock_data_dict.get(vt_symbol)
                    if data and day < len(data['close']):
                        sell_price = data['close'][day]
                        sell_value = positions[vt_symbol]['shares'] * sell_price
                        
                        # 计算交易成本
                        cost = self.calculate_trading_cost(sell_value, is_buy=False)
                        total_cost += cost
                        
                        cash += sell_value - cost
                        del positions[vt_symbol]
                        trade_count += 1
            
            # 买入新选中的股票
            target_position = cash * 0.1  # 每只10%
            
            for vt_symbol, ret, data in selected:
                if vt_symbol in positions:
                    continue
                
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
                        positions[vt_symbol] = {'shares': shares}
                        trade_count += 1
            
            # 计算当日总资产
            position_value = sum(
                positions[vt_symbol]['shares'] * stock_data_dict[vt_symbol]['close'][day]
                for vt_symbol in positions
                if vt_symbol in stock_data_dict and day < len(stock_data_dict[vt_symbol]['close'])
            )
            
            portfolio_value = cash + position_value
        
        total_return = (portfolio_value - 1000000.0) / 1000000.0
        
        return {
            'total_return': total_return,
            'total_cost': total_cost,
            'trade_count': trade_count,
            'rebalance_interval': rebalance_interval,
            'cost_ratio': total_cost / 1000000.0,
        }
    
    def analyze_cost_impact(self, stock_data_dict: Dict) -> Dict:
        """
        分析交易成本对收益的影响
        对比考虑成本和不考虑成本的情况
        """
        print("\n分析交易成本影响...")
        
        # 不考虑成本
        self.commission_rate = 0
        self.tax_rate = 0
        self.slippage = 0
        result_no_cost = self._backtest_with_frequency(stock_data_dict, 1)
        
        # 考虑成本
        self.commission_rate = 0.0003
        self.tax_rate = 0.001
        self.slippage = 0.001
        result_with_cost = self._backtest_with_frequency(stock_data_dict, 1)
        
        return {
            'no_cost': result_no_cost,
            'with_cost': result_with_cost,
            'cost_impact': result_no_cost['total_return'] - result_with_cost['total_return'],
        }
    
    def run_full_analysis(self, start_date: str = "2022-01-01",
                         end_date: str = "2024-01-01",
                         max_stocks: int = 100) -> Dict:
        """运行完整的成本分析"""
        
        print("="*60)
        print("交易成本敏感性分析")
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
        
        # 1. 调仓频率分析
        frequency_results = self.analyze_rebalance_frequency(
            stock_data_dict, 
            rebalance_intervals=[1, 5, 10, 20]
        )
        
        # 2. 成本影响分析
        cost_impact_results = self.analyze_cost_impact(stock_data_dict)
        
        return {
            'frequency_analysis': frequency_results,
            'cost_impact_analysis': cost_impact_results,
            'stock_count': len(stock_data_dict),
        }


def print_cost_analysis_results(results: Dict):
    """打印成本分析结果"""
    print("\n" + "="*60)
    print("交易成本敏感性分析报告")
    print("="*60)
    
    # 1. 调仓频率分析
    print("\n【调仓频率分析】")
    print("-"*60)
    print(f"{'调仓频率':<12} {'总收益':<12} {'交易成本':<12} {'交易次数':<10} {'成本占比':<10}")
    print("-"*60)
    
    freq_data = results.get('frequency_analysis', {})
    for key, data in sorted(freq_data.items(), key=lambda x: x[1]['rebalance_interval']):
        interval = data['rebalance_interval']
        print(f"每{interval:>3}天      {data['total_return']*100:>10.2f}%   "
              f"{data['total_cost']:>10.2f}    {data['trade_count']:>8}   "
              f"{data['cost_ratio']*100:>8.2f}%")
    
    # 2. 成本影响分析
    print("\n【交易成本影响分析】")
    print("-"*60)
    
    cost_data = results.get('cost_impact_analysis', {})
    no_cost = cost_data.get('no_cost', {})
    with_cost = cost_data.get('with_cost', {})
    impact = cost_data.get('cost_impact', 0)
    
    print(f"不考虑交易成本:")
    print(f"  总收益: {no_cost.get('total_return', 0)*100:.2f}%")
    print(f"  交易次数: {no_cost.get('trade_count', 0)}")
    
    print(f"\n考虑交易成本:")
    print(f"  总收益: {with_cost.get('total_return', 0)*100:.2f}%")
    print(f"  交易成本: {with_cost.get('total_cost', 0):.2f}")
    print(f"  交易次数: {with_cost.get('trade_count', 0)}")
    
    print(f"\n成本影响:")
    print(f"  收益侵蚀: {impact*100:.2f}%")
    print(f"  成本占比: {with_cost.get('cost_ratio', 0)*100:.2f}%")
    
    print("="*60)
    
    # 建议
    print("\n【优化建议】")
    print("-"*60)
    
    best_freq = min(freq_data.values(), key=lambda x: x['cost_ratio'])
    print(f"1. 最优调仓频率: 每{best_freq['rebalance_interval']}天")
    print(f"   可以降低成本占比至{best_freq['cost_ratio']*100:.2f}%")
    
    if impact > 0.05:
        print(f"2. 交易成本侵蚀严重({impact*100:.1f}%)，建议:")
        print("   - 降低调仓频率")
        print("   - 提高选股门槛，减少无效交易")
        print("   - 使用触发式调仓（只在信号变化时调仓）")
    else:
        print("2. 交易成本影响可控")
    
    print("="*60)


def main():
    """主函数"""
    print("="*60)
    print("A股多因子选股策略 - 交易成本敏感性分析")
    print("="*60)
    
    db_config = load_db_config()
    if not db_config:
        print("✗ 无法读取数据库配置")
        return
    
    db_manager = DatabaseManager(db_config)
    if not db_manager.db:
        print("✗ 数据库连接失败")
        return
    
    analyzer = CostAnalyzer(db_manager)
    
    results = analyzer.run_full_analysis(
        start_date="2022-01-01",
        end_date="2024-01-01",
        max_stocks=100
    )
    
    if results:
        print_cost_analysis_results(results)
        
        # 保存结果
        result_dir = "backtest_results"
        os.makedirs(result_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_file = os.path.join(result_dir, f"cost_analysis_{timestamp}.json")
        
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\n分析结果已保存到: {result_file}")
    else:
        print("\n分析失败")


if __name__ == "__main__":
    main()
