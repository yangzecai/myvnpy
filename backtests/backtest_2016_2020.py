#!/usr/bin/env python
"""
最终优化策略 - 2016-2020年回测
验证策略在牛市和不同市场环境下的表现
"""

import os
import sys
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from final_optimization import FinalBacktest, print_result
from factor_analysis import DatabaseManager, load_db_config


def main():
    """主函数"""
    print("="*60)
    print("A股多因子选股策略 - 2016-2020年回测")
    print("="*60)
    print("\n回测区间: 2016-01-01 ~ 2020-01-01")
    print("市场环境: 包含2015年股灾后的震荡市、2019-2020年结构性牛市")
    
    db_config = load_db_config()
    if not db_config:
        print("✗ 无法读取数据库配置")
        return
    
    db_manager = DatabaseManager(db_config)
    if not db_manager.db:
        print("✗ 数据库连接失败")
        return
    
    print("\n✓ 数据库连接成功")
    
    backtest = FinalBacktest(db_manager)
    
    result = backtest.run_backtest(
        start_date="2016-01-01",
        end_date="2020-01-01",
        initial_capital=1000000.0,
        max_stocks=100
    )
    
    if result:
        print_result(result)
        
        # 保存结果
        result_dir = "backtest_results"
        os.makedirs(result_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_file = os.path.join(result_dir, f"final_strategy_2016_2020_{timestamp}.json")
        
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"\n结果已保存到: {result_file}")
        
        # 打印对比信息
        print("\n" + "="*60)
        print("周期对比")
        print("="*60)
        print("2022-2024年 (熊市): 夏普率 1.22, 收益 30.06%")
        sharpe = result.get('sharpe_ratio', 0)
        total_ret = result.get('total_return', 0) * 100
        print(f"2016-2020年 (牛熊): 夏普率 {sharpe:.2f}, 收益 {total_ret:.2f}%")
        print("="*60)
    else:
        print("\n回测失败")


if __name__ == "__main__":
    main()
