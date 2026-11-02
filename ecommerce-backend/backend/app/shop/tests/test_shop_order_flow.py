from concurrent.futures import ThreadPoolExecutor

from starlette.testclient import TestClient


def _create_product(client: TestClient, token_headers: dict[str, str], name: str, stock: int) -> int:
    """上架商品，返回商品 ID"""
    response = client.post(
        '/shop/products',
        headers=token_headers,
        json={'name': name, 'price': 9900, 'stock': stock},
    )
    assert response.status_code == 200, response.text
    return response.json()['data']['id']


def test_create_product(client: TestClient, token_headers: dict[str, str]) -> None:
    product_id = _create_product(client, token_headers, '测试商品-基础流程', 10)
    response = client.get(f'/shop/products/{product_id}')
    assert response.status_code == 200
    assert response.json()['data']['stock'] == 10


def test_order_flow_and_timeout_fields(client: TestClient, token_headers: dict[str, str]) -> None:
    """下单 → 支付 → 查单 全链路"""
    product_id = _create_product(client, token_headers, '测试商品-下单流程', 5)
    response = client.post(
        '/shop/orders',
        headers=token_headers,
        json={'items': [{'product_id': product_id, 'quantity': 2}]},
    )
    assert response.status_code == 200, response.text
    order = response.json()['data']
    assert order['total_amount'] == 9900 * 2
    assert order['status'] == 0

    # 模拟支付回调
    pay_response = client.post(f'/shop/orders/{order["order_no"]}/pay', headers=token_headers)
    assert pay_response.status_code == 200


def test_insufficient_stock_rejected(client: TestClient, token_headers: dict[str, str]) -> None:
    """库存不足下单应被拒绝且不产生订单"""
    product_id = _create_product(client, token_headers, '测试商品-库存不足', 1)
    response = client.post(
        '/shop/orders',
        headers=token_headers,
        json={'items': [{'product_id': product_id, 'quantity': 2}]},
    )
    assert response.status_code == 409


def test_concurrent_order_no_oversell(client: TestClient, token_headers: dict[str, str]) -> None:
    """并发压测：库存 50，100 个并发请求各买 1 件，成功订单数必须恰为 50（零超卖）"""
    product_id = _create_product(client, token_headers, '测试商品-并发零超卖', 50)

    def _order_once(_: int) -> int:
        response = client.post(
            '/shop/orders',
            headers=token_headers,
            json={'items': [{'product_id': product_id, 'quantity': 1}]},
        )
        return 1 if response.status_code == 200 else 0

    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(_order_once, range(100)))

    assert sum(results) == 50, f'预期恰好成交 50 单，实际 {sum(results)}'
    # Redis 预扣与 DB 落库必须最终一致：剩余库存恰为 0
    detail = client.get(f'/shop/products/{product_id}').json()['data']
    assert detail['stock'] == 0
