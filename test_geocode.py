#!/usr/bin/env python
"""
Script test API geocode
"""
import requests
import json

def test_geocode_api():
    """Test api_geocode_address"""
    
    # Test addresses
    test_addresses = [
        "Hồ Chí Minh",
        "250 Trần Hưng Đạo, Quận 1",
        "Cà Phê Phin Hà Nội",
        "Nhà hát Lớn Hà Nội"
    ]
    
    for address in test_addresses:
        print(f"\n{'='*60}")
        print(f"Tìm kiếm: {address}")
        print('='*60)
        
        try:
            # Call local API
            url = f"http://localhost:8000/api/geocode-address/?q={address}"
            print(f"URL: {url}")
            
            response = requests.get(url, timeout=10)
            print(f"Status: {response.status_code}")
            
            data = response.json()
            print(f"Response: {json.dumps(data, indent=2, ensure_ascii=False)}")
            
            if 'lat' in data and 'lng' in data:
                print(f"✓ Tọa độ: ({data['lat']}, {data['lng']})")
            else:
                print("✗ Không lấy được tọa độ")
                
        except Exception as e:
            print(f"✗ Lỗi: {e}")

if __name__ == "__main__":
    print("Bắt đầu test API geocode...")
    test_geocode_api()
    print("\n\nTest hoàn thành!")
