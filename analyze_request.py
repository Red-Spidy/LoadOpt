import json

with open('postman_sample_request.json', 'r') as f:
    data = json.load(f)

items = data['items']
stop1_items = [i for i in items if i['delivery']['stop_number'] == 1]
stop2_items = [i for i in items if i['delivery']['stop_number'] == 2]

stop1_count = sum(i['quantity'] for i in stop1_items)
stop2_count = sum(i['quantity'] for i in stop2_items)
total_count = stop1_count + stop2_count

print(f"=== REQUEST ANALYSIS ===")
print(f"Total item types: {len(items)}")
print(f"Total items: {total_count}")
print(f"Stop 1 items: {stop1_count}")
print(f"Stop 2 items: {stop2_count}")
print()
print(f"Container: {data['container']['type']}")
print(f"Container dimensions: {data['container']['dimensions']['length']}x{data['container']['dimensions']['width']}x{data['container']['dimensions']['height']} cm")
print()
print("Stop 1 SKUs:")
for item in stop1_items:
    dims = item['dimensions']
    print(f"  - {item['sku']}: {dims['length']}x{dims['width']}x{dims['height']}cm, {item['weight']['value']}kg, qty={item['quantity']}")
print()
print("Stop 2 SKUs:")
for item in stop2_items:
    dims = item['dimensions']
    print(f"  - {item['sku']}: {dims['length']}x{dims['width']}x{dims['height']}cm, {item['weight']['value']}kg, qty={item['quantity']}")
