import asyncio
import logging

logger = logging.getLogger("Transport")

class UDPReceiverProtocol(asyncio.DatagramProtocol):
    def __init__(self, packet_queue: asyncio.Queue):
        self.packet_queue = packet_queue

    def connection_made(self, transport):
        self.transport = transport
        logger.info("UDP transport endpoint bound successfully")

    def datagram_received(self, data, addr):
        try:
            self.packet_queue.put_nowait((data, addr))
        except asyncio.QueueFull:
            # Under a severe flood, drop older packets rather than crashing
            pass

    def error_received(self, exc):
        logger.error(f"UDP socket error received: {exc}")

async def start_udp_receiver(port: int, packet_queue: asyncio.Queue, sock=None) -> asyncio.DatagramTransport:
    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: UDPReceiverProtocol(packet_queue),
        local_addr=None if sock else ("0.0.0.0", port),
        sock=sock
    )
    return transport
