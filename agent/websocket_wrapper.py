import asyncio
import logging
import select
import socket
import threading
import time
import traceback
from abc import ABC, abstractmethod
from collections import deque
from typing import Optional

import websocket
import websockets

logger = logging.getLogger(__name__)


class WebsocketWrapper(ABC):
    def __init__(self, websocket_url, websocket_port: Optional[int] = None, **kwargs):
        if kwargs:
            logger.warning(
                "WebsocketWrapper is initilized with unused arguments: %s", kwargs
            )
        self._websocket_url = websocket_url
        self._websocket_port = websocket_port

        self._message_handler = None
        self._incoming_message_process_thread: Optional[threading.Thread] = None
        self._incoming_messages = deque(maxlen=1000)  # Queue for incoming messages
        self._incoming_messages_count = 0
        self._processed_incoming_messages_count = 0
        self._running = False
        self.server_ready = threading.Event()
        self.running_lock = threading.Lock()

    # TODO: we should consider use threading.Event to control the running status.
    @property
    def running(self):
        with self.running_lock:
            return self._running
        
    @running.setter
    def running(self, value):
        with self.running_lock:
            self._running = value

    def start(self):
        self.running = True
        self._start_impl()

    @abstractmethod
    def _start_impl(self):
        pass

    def stop(self):
        logger.info("[SYSTEM] Stopping websocket wrapper...")
        self.running = False

        # Join the incoming message processing thread
        if self._incoming_message_process_thread:
            self._incoming_message_process_thread.join()

        self._stop_impl()
        logger.info("[SYSTEM] Websocket wrapper stopped.")

    @abstractmethod
    def _stop_impl(self):
        pass

    @abstractmethod
    def send_text_message(self, message):
        pass

    def get_stats(self):
        basic_stats = {
            "running": self.running,
            "incoming_messages_count": self._incoming_messages_count,
            "processed_incoming_messages_count": self._processed_incoming_messages_count,
        }
        additional_stats = self._get_additional_stats()
        return {**basic_stats, **additional_stats}

    @abstractmethod
    def _get_additional_stats(self):
        pass

    def set_message_handler(self, handler):
        if self._message_handler:
            logger.warning("A handler is already set, skipping")
            return
        self._message_handler = handler

        def run_in_thread():
            try:
                asyncio.set_event_loop(asyncio.new_event_loop())
                loop = asyncio.get_event_loop()
                loop.run_until_complete(self._process_incoming_messages())
            except asyncio.CancelledError:
                pass
            finally:
                loop.run_until_complete(loop.shutdown_asyncgens())
                loop.close()

        self._incoming_message_process_thread = threading.Thread(
            target=run_in_thread
        )
        self._incoming_message_process_thread.start()

    async def _process_incoming_messages(self):
        logger.info("[SYSTEM] Starting processing incoming messages loop...")
        while self.running:
            if self._incoming_messages and self._message_handler:
                message = self._incoming_messages.popleft()
                self._message_handler(message)
                self._processed_incoming_messages_count += 1
            else:
                await asyncio.sleep(0.005)
        logger.info("[SYSTEM] Stopping processing incoming messages loop...")

    def receive_message(self, message):
        self._incoming_messages_count += 1
        self._incoming_messages.append(message)
        if (
            len(self._incoming_messages) >= 1000
            and len(self._incoming_messages) % 100
            and self.running
        ):
            logger.warning(
                f"Incoming message queue is long {len(self._incoming_messages)}, agents may be stuck."
            )
            raise Exception("Incoming message queue is full, agents may be stuck.")

    def wait_for_ready(self, timeout=None):
        """Wait for the server to be ready with a possible timeout."""
        logger.info("Waiting for the server to be ready...")
        self.server_ready.wait(timeout)


class StandaloneWebsocketServerWrapper(WebsocketWrapper):
    def __init__(self, websocket_url, websocket_port, **kwargs):
        super().__init__(
            websocket_port=websocket_port,
            websocket_url=websocket_url,
        )
        if kwargs:
            logger.warning(
                "StandaloneWebsocketServerWrapper is initilized with unused arguments: %s",
                kwargs,
            )
        self._outgoing_messages = deque(maxlen=1000)  # Queue for outgoing messages
        self._outgoing_messages_count = 0
        self._processed_outgoing_messages_count = 0

        self._server_thread = None
        self._server_loop = None
        self._websocket_server = None
        self._websocket_client = None

    def run_server(self):
        self._server_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._server_loop)
        start_server = websockets.serve(
            self.handler,
            self._websocket_url,
            self._websocket_port,
            ping_interval=180,
            ping_timeout=30,
        )
        self._websocket_server = self._server_loop.run_until_complete(start_server)
        logger.info(
            f"Websocket server started at {self._websocket_url}:{self._websocket_port}"
        )
        self.server_ready.set()
        logger.info("Server is ready to accept messages.")
        self._server_loop.run_forever()

    def _start_impl(self):
        self._server_thread = threading.Thread(target=self.run_server)
        self._server_thread.start()

    def _stop_impl(self):
        if self._websocket_server and self._server_loop:

            # Close the websocket server
            self._websocket_server.close()

            # Wait for the server to close
            asyncio.run_coroutine_threadsafe(self._websocket_server.wait_closed(), self._server_loop)
            
            # Stop the event loop
            self._server_loop.call_soon_threadsafe(self._server_loop.stop)

        if self._server_thread:
            self._server_thread.join()  # Wait for the server thread to finish

    def send_text_message(self, message):
        logger.debug(f"Preparing to send message: {message}")
        print(f"Added to queue: {message}")
        self._outgoing_messages_count += 1
        self._outgoing_messages.append(message)
        if (
            len(self._outgoing_messages) >= 1000
            and len(self._outgoing_messages) % 100
            and self.running
        ):
            logger.warning(
                f"Outgoing message queue is long {len(self._outgoing_messages)}, the environment may be stuck."
            )
            raise Exception(
                "Outgoing message queue is full, the environment may be stuck."
            )
        if len(self._outgoing_messages) > 5:
            logger.info(
                f"Outgoing message queue size: {len(self._outgoing_messages)}"
            )

    def get_incoming_message_queue(self):
        return list(self._incoming_messages)

    async def process_outgoing_messages(self, websocket):
        while self.running:
            if (
                self._outgoing_messages
                and self._websocket_client
                and self._websocket_client.open
            ):
                message = self._outgoing_messages.popleft()
                print(f"Retrieved message")
                start = time.time()
                await websocket.send(message)
                print(f"Sent message after {int(time.time()-start)} s")
                self._processed_outgoing_messages_count += 1
            else:
                await asyncio.sleep(0.005)  # Allows handling of other tasks

    async def handler(self, websocket, path):
        self._websocket_client = websocket
        client_address = websocket.remote_address[0]  # Get the client's IP address
        logging.info(f"Client connected: {client_address}")
        try:
            # Run tasks for processing incoming and outgoing messages concurrently
            outgoing_task = asyncio.create_task(
                self.process_outgoing_messages(websocket)
            )
            incoming_task = asyncio.create_task(self.process_incoming(websocket))
            await asyncio.gather(outgoing_task, incoming_task)
        finally:
            logger.info(f"Client disconnected: {client_address}")
            self._websocket_client = None

    async def process_incoming(self, websocket):
        async for message in websocket:
            self.receive_message(message)

    def _get_additional_stats(self):
        return {
            "outgoing_messages_count": self._outgoing_messages_count,
            "processed_outgoing_messages_count": self._processed_outgoing_messages_count,
        }


class ExternalWebsocketServerWrapper(WebsocketWrapper):
    """Websocket wrapper for connecting to an external websocket server."""
    MAX_RECONNECT_ATTEMPT = 3

    def __init__(self, websocket_url, websocket_port: Optional[int] = None, simulation_id="01234", **kwargs):
        super().__init__(
            websocket_port=websocket_port,
            websocket_url=websocket_url,
        )
        if kwargs:
            logger.warning(
                "ExternalWebsocketServerWrapper is initilized with unused arguments: %s",
                kwargs,
            )
        self._simulation_id = simulation_id
        self._websocket_client = None
        self._incoming_message_accumulate_thread = None
        self._close_event = threading.Event()

        self._receive_buffer_size = 1024 * 1024 * 5  # 10 MB
        self._send_buffer_size = 1024 * 1024 * 5  # 10 MB
        self._max_retries = 3
        self._retry_delay = 50  # ms

        self._retry_count = 0
        self._reconnect_count = 0
        self._outgoing_messages_count = 0
        logger.info(
            f"websocket_port is ignored: {websocket_port}, please specify the port in the URL."
        )
        # TODO: hack here, read_index=1000000 is just put a very large number to avoid the server to send the old messages
        self._connection_url = f"ws://{self._websocket_url}/agent-observations?simulation_id={self._simulation_id}&read_index=1000000"

    def _start_impl(self):
        self._reconnect()

    def _reconnect(self):
        """Handle the websocket reconnection."""
        if not self.running:
            return
        if self._reconnect_count == self.MAX_RECONNECT_ATTEMPT:
            logger.error(
                f"Failed to reconnect after {self.MAX_RECONNECT_ATTEMPT} attempts."
            )
            self.stop()
        try:
            self._reconnect_count += 1
            logger.info(f"Connecting to the websocket server: {self._connection_url}, connection count: {self._reconnect_count}")
            self._websocket_client = websocket.create_connection(
                self._connection_url,
                sockopt=[
                    (socket.SOL_SOCKET, socket.SO_RCVBUF, self._receive_buffer_size),
                    (socket.SOL_SOCKET, socket.SO_SNDBUF, self._send_buffer_size),
                ],
            )
            if (
                not self._incoming_message_accumulate_thread
                or not self._incoming_message_accumulate_thread.is_alive()
            ):
                self._incoming_message_accumulate_thread = threading.Thread(
                    target=self._process_incoming
                )
                self._incoming_message_accumulate_thread.start()

            self.server_ready.set()
            self._reconnect_count = 0
            logger.info(f"Connected to the websocket server: {self._connection_url}, reset connection count, {self._reconnect_count=}.")
        except Exception as e:
            logging.error(f"Failed to connect to the websocket server: {e}")
            # Implement a backoff strategy or a delay before retrying if needed
            time.sleep(
                5
            )  # Simple fixed delay, consider exponential backoff for production
            self._reconnect()

    def _stop_impl(self):

        # TODO: Make sure that this function is idempotent
        self._close_event.set()
        if self._websocket_client:
            self._websocket_client.close()
        if self._incoming_message_accumulate_thread:
            self._incoming_message_accumulate_thread.join()

    def _process_incoming(self):
        while self.running and self._websocket_client:
            try:
                readable, _, _ = select.select([self._websocket_client.sock], [], [], 3)
                if readable:
                    message = self._websocket_client.recv()
                    self.receive_message(message)
                if self._close_event.is_set():
                    break
            except websocket.WebSocketConnectionClosedException as e:
                logging.error(f"WebSocket connection closed when processing incoming message. Attempting to reconnect... error: {e}")
                self._reconnect()
            except Exception as e:
                logging.error(f"Error in receiving message: {e}")
                break

    def send_text_message(self, message):
        if self.running and self._websocket_client:
            # Send the message through the websocket with retries
            for i in range(self._max_retries):
                try:
                    if i > 0:
                        logging.info(f"Retrying to send message: {message}")
                        self._retry_count += 1
                    self._websocket_client.send(message)
                    self._outgoing_messages_count += 1
                    break
                except websocket.WebSocketConnectionClosedException as e:
                    logging.error(
                        f"WebSocket connection closed when sending text. Attempting to reconnect... error: {e}"
                    )
                    self._reconnect()
                except Exception as e:
                    stack_trace = traceback.format_exc()
                    logging.error(f"Error in sending message: {e}, {stack_trace}")
                    time.sleep(self._retry_delay / 1000)
                if i == self._max_retries - 1:
                    logging.error(
                        f"Failed to send message after {self._max_retries} retries."
                    )
        else:
            logging.error(
                "WebSocket connection is not established. Attempting to reconnect..."
            )
            self._reconnect()

    def _get_additional_stats(self):
        return {
            "outgoing_messages_count": self._outgoing_messages_count,
        }
