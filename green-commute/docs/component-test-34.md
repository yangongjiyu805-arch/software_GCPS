# 组件3、4测试

本文件对应《测试报告》第2部分的组件3“积分账本与兑换退款组件”和组件4“商户经营与库存履约组件”。测试代码位于 tests/test_component_34.py。两张测试表各从1开始编号，每个测试函数对应一条记录。

## 组件3 积分账本与兑换退款

| 报告记录 | 测试函数 | 核验内容 |
| --- | --- | --- |
| 1 | test_component3_01_insufficient_points | 积分不足时拒绝兑换，订单、余额和库存不变 |
| 2 | test_component3_02_redeem_deducts_points_and_stock | 兑换成功后生成待核销订单，积分和库存按规则扣减 |
| 3 | test_component3_03_sold_out_does_not_charge | 商品售罄时拒绝兑换，不扣积分、不生成订单 |
| 4 | test_component3_04_refund_restores_points_and_stock | 核销前退款，退回积分并回补库存，写入退款流水 |
| 5 | test_component3_05_fulfilled_order_cannot_be_refunded | 已核销订单不能退款，积分和库存不变 |
| 6 | test_component3_06_repeated_refund_is_idempotent | 重复退款不会再次增加积分或库存 |
| 7 | test_component3_07_trip_business_id_prevents_duplicate_award | 同一行程编号防止重复奖励；编号相同但内容变更时拒绝 |
| 8 | test_component3_08_zero_point_trip_has_no_ledger_entry | 零积分行程保留行程记录，不产生虚假积分流水 |
| 9 | test_component3_09_wallet_summary_matches_ledger | 账本余额与奖励、兑换、退款流水合计一致 |
| 10 | test_component3_10_wallet_cursor_pagination | 按游标分页查询积分流水，不重复或漏掉记录 |

## 组件4 商户经营与库存履约

| 报告记录 | 测试函数 | 核验内容 |
| --- | --- | --- |
| 1 | test_component4_01_merchant_publishes_product | 商户发布商品后，居民商城可查询到商品 |
| 2 | test_component4_02_blank_product_name_is_rejected | 空白商品名称被拒绝，不创建商品 |
| 3 | test_component4_03_zero_inventory_adjustment_is_rejected | 库存调整量为0时被拒绝，库存及流水不变 |
| 4 | test_component4_04_inventory_cannot_be_overdrawn | 扣减超过当前库存时被拒绝，不产生负库存 |
| 5 | test_component4_05_repeated_restock_adds_stock_once | 相同操作编号重复补货，只增加一次库存 |
| 6 | test_component4_06_unlisted_product_is_hidden_from_residents | 商品下架后，商户可见记录，居民商城不再展示 |
| 7 | test_component4_07_merchant_cannot_read_other_store_inventory | 另一商户不能查看本商户商品的库存 |
| 8 | test_component4_08_owner_merchant_fulfills_order | 商品所属商户核销订单，记录核销状态和时间 |
| 9 | test_component4_09_repeated_fulfillment_keeps_original_time | 重复核销保持首次核销时间，不重复生成订单 |
| 10 | test_component4_10_inventory_query_returns_current_stock_and_history | 库存查询返回当前数量和对应调整流水 |

## 运行方法与结果

在 green-commute 目录中安装 requirements-dev.txt 所列测试依赖，然后执行：

    python -m pytest -q tests/test_component_34.py

tests/conftest.py 在导入应用前将数据库指向独立的临时 SQLite 文件；每个测试函数重新建立演示数据。2026年11月21日对当前仓库版本运行上述20条组件测试，结果为 20 passed、1 warning。该 warning 是 starlette.testclient 与 httpx 的依赖弃用提示，没有失败的测试断言。

流程图上的数字是测试报告的路径标识；代码函数名中的序号对应测试表记录编号。
