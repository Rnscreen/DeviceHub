"""校验码计算工具"""

def calculate_crc16(data: bytes) -> bytes:
    """计算CRC16校验码(Modbus协议标准)"""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc.to_bytes(2, 'little')

def calculate_crc32(data: bytes) -> bytes:
    """计算CRC32校验码"""
    crc = 0xFFFFFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xEDB88320
            else:
                crc >>= 1
    crc ^= 0xFFFFFFFF
    return crc.to_bytes(4, 'little')

def calculate_lrc(data: bytes) -> bytes:
    """计算LRC(纵向冗余校验)校验码"""
    lrc = 0
    for byte in data:
        lrc = (lrc + byte) & 0xFF
    lrc = (-lrc) & 0xFF
    return lrc.to_bytes(1, 'big')

def calculate_checksum(data: bytes) -> bytes:
    """计算自定义校验码"""
    return bytes([sum(data) % 256])

def calculate_crc16_ccitt(data: bytes) -> bytes:
    """计算CRC-CCITT(XModem)校验码"""
    crc = 0x0000
    for byte in data:
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc.to_bytes(2, 'big')


# 添加测试函数
def test_checksums():
    """测试各种校验码计算功能"""
    test_data = b"Hello, World!"
    
    print(f"测试数据: {test_data}")
    print(f"CRC16: {calculate_crc16(test_data).hex()}")
    print(f"CRC32: {calculate_crc32(test_data).hex()}")
    print(f"LRC: {calculate_lrc(test_data).hex()}")
    print(f"Checksum: {calculate_checksum(test_data).hex()}")
    print(f"CRC16-CCITT: {calculate_crc16_ccitt(test_data).hex()}")
    
    # 验证一些已知值
    assert calculate_lrc(b"123456789") == bytes.fromhex("23")
    assert calculate_checksum(b"123456789") == bytes.fromhex("dd")
    assert calculate_crc16_ccitt(b"123456789") == bytes.fromhex("31c3")
    
    
    print("\n所有测试通过!")

if __name__ == "__main__":
    test_checksums()