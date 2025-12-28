# 动作执行差异分析

## 当前训练代码 vs 真实服务器

### 1. **Scoring动作**

#### 训练代码（简化版）
```python
# 简单曼哈顿距离移动
dx = 1 if target[0] > player["posX"] else -1 if target[0] < player["posX"] else 0
dy = 1 if target[1] > player["posY"] else -1 if target[1] < player["posY"] else 0
direction = "right" if dx > 0 else "left" if dx < 0 else ("down" if dy > 0 else "up")
```

#### 真实服务器（复杂版）
```python
# 使用A*路径规划
path = improved_route(player_pos, target)
# 考虑：
# - 障碍物避让
# - 敌方领地权重
# - 在敌方领地时的特殊处理
# - 距离敌人<=3时的防御逻辑
```

**差异影响：**
- ❌ 训练时可能走直线撞墙
- ❌ 无法学习绕过障碍物的策略
- ❌ 在敌方领地时行为不一致
- ✅ 但训练速度快10-100倍

---

### 2. **Defence动作**

#### 训练代码（简化版）
```python
# 直接向第一个敌人移动
enemy = enemies[0]
dx = 1 if enemy["posX"] > player["posX"] else -1
dy = 1 if enemy["posY"] > player["posY"] else -1
```

#### 真实服务器（复杂版）
```python
# 使用防御专用路径规划
path = defence_route(player_pos, opponent_pos)
# 考虑：
# - 预测敌人路径（如果敌人有flag，预测其返回路径）
# - 拦截策略（在中轴线拦截）
# - 只在己方半场行动
# - 敌人去flag时的路径预测
```

**差异影响：**
- ❌ 训练时无法学习拦截策略
- ❌ 可能进入敌方领地（导致死亡）
- ❌ 无法学习预测性防御
- ✅ 但训练速度快

---

### 3. **Saving动作**

#### 训练代码（简化版）
```python
# 直接向prison移动
prison = prisons[0]
dx = 1 if prison[0] > player["posX"] else -1
dy = 1 if prison[1] > player["posY"] else -1
```

#### 真实服务器（复杂版）
```python
# 使用路径规划到prison
path = improved_route(player_pos, prison_pos)
# 考虑：
# - 障碍物避让
# - 最优路径选择
```

**差异影响：**
- ⚠️ 影响较小（prison位置固定）
- ❌ 但可能走非最优路径

---

## 影响评估

### 负面影响
1. **环境不匹配**：训练环境与真实环境差异大
2. **策略过拟合**：模型学习的是简单移动，而非真实策略
3. **泛化能力差**：在真实环境中表现可能下降
4. **无法学习复杂策略**：拦截、预测等高级策略无法学习

### 正面影响
1. **训练速度快**：简单移动比路径规划快10-100倍
2. **并行训练更有效**：简单逻辑适合多进程
3. **快速迭代**：可以快速测试不同超参数

---

## 权衡建议

### 方案1：保持简化（当前方案）
**适用场景：**
- 快速原型开发
- 超参数调优
- 算法验证

**优点：**
- 训练速度快
- 并行效率高
- 代码简单

**缺点：**
- 环境不匹配
- 需要迁移学习

---

### 方案2：使用真实路径规划
**适用场景：**
- 生产环境部署
- 追求最佳性能
- 长期训练

**优点：**
- 环境匹配
- 策略更真实
- 泛化能力强

**缺点：**
- 训练速度慢（可能慢10-100倍）
- 并行效率低
- 代码复杂

---

### 方案3：混合方案（推荐）
**策略：**
1. **前期训练**：使用简化版快速训练，学习基本策略
2. **后期微调**：使用真实路径规划进行微调
3. **渐进式迁移**：逐步增加复杂度

**实现：**
```python
USE_REAL_PATHFINDING = False  # 前期False，后期True

if USE_REAL_PATHFINDING:
    # 使用真实的defence/scoring/saving函数
    direction = defence(player, target)
else:
    # 使用简化的移动逻辑
    direction = simple_move(player, target)
```

**优点：**
- 兼顾速度和真实性
- 渐进式学习
- 灵活性高

**缺点：**
- 需要两套代码
- 需要手动切换

---

## 推荐方案

**当前阶段：保持简化版**
- 快速训练和验证
- 并行训练效率高
- 可以快速迭代

**未来优化：**
1. 训练到一定阶段后，切换到真实路径规划进行微调
2. 或者实现混合方案，让模型适应两种环境

