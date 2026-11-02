-- 库存原子扣减脚本：比较-扣减在 Redis 内一次完成，天然避免「先 GET 再 SET」的竞态
-- KEYS[1] = 库存键 shop:stock:{product_id}
-- ARGV[1] = 本次扣减数量
local stock = tonumber(redis.call('GET', KEYS[1]) or '-1')
if stock == -1 then
    return -1   -- 库存键不存在（商品未预热或已过期）
end
if stock < tonumber(ARGV[1]) then
    return -2   -- 库存不足
end
redis.call('DECRBY', KEYS[1], ARGV[1])
return stock - tonumber(ARGV[1])
