#!/usr/bin/env python3
"""
测试状态特征向量维度是否正确
验证玩家在prison中时状态向量的维度
"""

import sys
import os
# 添加父目录到路径，以便访问 lib/
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(SCRIPT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from lib import RL
import numpy as np

# 创建一个模拟的world对象
class MockWorld:
    def __init__(self):
        self.width = 50
        self.height = 30
        self.middle_line = 25
        self.my_team_name = "L"
    
    def list_flags(self, mine, canPickup):
        # 返回一些模拟的flag
        if mine:
            return [
                {"posX": 5, "posY": 5, "canPickup": True},
                {"posX": 10, "posY": 10, "canPickup": False}
            ]
        else:
            return [
                {"posX": 45, "posY": 25, "canPickup": True}
            ]
    
    def list_targets(self, mine):
        if mine:
            return [(5, 5), (10, 10)]
        else:
            return [(45, 25)]
    
    def list_players(self, mine, inPrison, hasFlag):
        if mine:
            if inPrison:
                return [{"posX": 2, "posY": 2, "hasFlag": False, "inPrison": True, "name": "L0"}]
            else:
                return [{"posX": 15, "posY": 15, "hasFlag": False, "inPrison": False, "name": "L1"}]
        else:
            if inPrison:
                return []
            else:
                return [{"posX": 35, "posY": 15, "hasFlag": False, "inPrison": False, "name": "R0"}]
    
    def list_prisons(self, mine):
        if mine:
            return [(2, 2), (2, 3)]
        else:
            return [(48, 28), (48, 29)]

# 测试函数
def test_state_dimension():
    print("=" * 60)
    print("测试状态特征向量维度")
    print("=" * 60)
    
    world = MockWorld()
    
    # 测试1: 正常玩家（不在prison）
    print("\n[测试1] 正常玩家（不在prison）")
    player1 = {
        "name": "L0",
        "posX": 15,
        "posY": 15,
        "hasFlag": False,
        "inPrison": False,
        "team": "L"
    }
    state1 = RL.extract_state_features(player1, world)
    print(f"  状态维度: {len(state1)} (期望: 19)")
    assert len(state1) == 19, f"状态维度错误: {len(state1)} != 19"
    print("  ✅ 通过")
    
    # 测试2: 玩家在prison中
    print("\n[测试2] 玩家在prison中")
    player2 = {
        "name": "L1",
        "posX": 2,
        "posY": 2,
        "hasFlag": False,
        "inPrison": True,
        "team": "L"
    }
    state2 = RL.extract_state_features(player2, world)
    print(f"  状态维度: {len(state2)} (期望: 19)")
    assert len(state2) == 19, f"状态维度错误: {len(state2)} != 19"
    print("  ✅ 通过")
    
    # 测试3: 玩家有flag
    print("\n[测试3] 玩家有flag")
    player3 = {
        "name": "L2",
        "posX": 20,
        "posY": 20,
        "hasFlag": True,
        "inPrison": False,
        "team": "L"
    }
    state3 = RL.extract_state_features(player3, world)
    print(f"  状态维度: {len(state3)} (期望: 19)")
    assert len(state3) == 19, f"状态维度错误: {len(state3)} != 19"
    print("  ✅ 通过")
    
    # 测试4: 玩家在prison中且有flag（理论上不应该发生，但测试一下）
    print("\n[测试4] 玩家在prison中且有flag（边界情况）")
    player4 = {
        "name": "L3",
        "posX": 2,
        "posY": 2,
        "hasFlag": True,
        "inPrison": True,
        "team": "L"
    }
    state4 = RL.extract_state_features(player4, world)
    print(f"  状态维度: {len(state4)} (期望: 19)")
    assert len(state4) == 19, f"状态维度错误: {len(state4)} != 19"
    print("  ✅ 通过")
    
    # 测试5: 验证特征向量的组成部分
    print("\n[测试5] 验证特征向量的组成部分")
    print(f"  玩家自身信息 (5维): {state1[0:5]}")
    print(f"  目标信息 (6维): {state1[5:11]}")
    print(f"  对手信息 (4维): {state1[11:15]}")
    print(f"  全局信息 (4维): {state1[15:19]}")
    print("  ✅ 通过")
    
    print("\n" + "=" * 60)
    print("✅ 所有测试通过！状态特征向量维度正确 (19维)")
    print("=" * 60)

if __name__ == "__main__":
    try:
        test_state_dimension()
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

