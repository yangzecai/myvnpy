#!/usr/bin/env python
"""
VeighNa Trader 启动脚本
在项目目录下运行此脚本启动 VeighNa Trader
"""

import sys
from pathlib import Path


def main():
    """主函数"""
    # 创建QApplication
    from vnpy.trader.ui import create_qapp
    qapp = create_qapp()
    
    # 创建事件引擎
    from vnpy.event import EventEngine
    event_engine = EventEngine()
    
    # 创建主引擎
    from vnpy.trader.engine import MainEngine
    main_engine = MainEngine(event_engine)
    
    # 添加CTA策略模块
    from vnpy_ctastrategy import CtaStrategyApp
    main_engine.add_app(CtaStrategyApp)
    
    from vnpy_ctabacktester import CtaBacktesterApp
    main_engine.add_app(CtaBacktesterApp)

    # 创建主窗口
    from vnpy.trader.ui import MainWindow
    main_window = MainWindow(main_engine, event_engine)
    main_window.showMaximized()
    
    # 运行
    qapp.exec()


if __name__ == "__main__":
    main()
