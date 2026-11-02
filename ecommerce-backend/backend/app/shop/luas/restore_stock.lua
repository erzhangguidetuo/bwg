-- 取消订单时归还库存
-- KEYS[1] = 库存键 shop:stock:{product_id}
-- ARGV[1] = 归还数量
local stock = tonumber(redis.call('GET', KEYS[1]) or '0')
redis.call('SET', KEYS[1], stock + tonumber(ARGV[1]))
return stock + tonumber(ARGV[1])
