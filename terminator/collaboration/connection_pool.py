"""
Connection Pool Module - Provides WebSocket connection pooling for collaborative editing
"""

import asyncio
import time
import logging
import uuid
from typing import Dict, List, Set, Optional, Any, Callable, Awaitable, Tuple, Union
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

class ConnectionPoolManager:
    """Manages WebSocket connection pools for improved performance and scalability"""
    
    def __init__(self, 
                 max_connections_per_pool: int = 100,
                 max_pools: int = 10,
                 idle_timeout: int = 300):
        """
        Initialize a connection pool manager
        
        Args:
            max_connections_per_pool: Maximum connections per pool
            max_pools: Maximum number of pools
            idle_timeout: Timeout for idle connections in seconds
        """
        self.max_connections_per_pool = max_connections_per_pool
        self.max_pools = max_pools
        self.idle_timeout = idle_timeout
        self.pools: Dict[str, 'ConnectionPool'] = {}
        self.pool_usage: Dict[str, int] = {}  # pool_id -> usage count
        self.client_to_pool: Dict[str, str] = {}  # client_id -> pool_id
        self.session_to_pool: Dict[str, str] = {}  # session_id -> pool_id
        self.cleanup_task = None
        
    async def start(self) -> None:
        """Start the pool manager and background tasks"""
        self.cleanup_task = asyncio.create_task(self._cleanup_pools())
        
    async def stop(self) -> None:
        """Stop the pool manager and background tasks"""
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
                
        # Stop all pools
        for pool in self.pools.values():
            await pool.stop()
        
    async def _cleanup_pools(self) -> None:
        """Periodically clean up idle pools"""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                # Find idle pools
                current_time = time.time()
                idle_pools = []
                for pool_id, pool in self.pools.items():
                    if current_time - pool.last_activity > self.idle_timeout:
                        idle_pools.append(pool_id)
                
                # Remove idle pools
                for pool_id in idle_pools:
                    pool = self.pools.pop(pool_id, None)
                    if pool:
                        await pool.stop()
                        self.pool_usage.pop(pool_id, None)
                        logger.info(f"Removed idle connection pool: {pool_id}")
                        
                        # Update mappings
                        for client_id, client_pool_id in list(self.client_to_pool.items()):
                            if client_pool_id == pool_id:
                                self.client_to_pool.pop(client_id, None)
                                
                        for session_id, session_pool_id in list(self.session_to_pool.items()):
                            if session_pool_id == pool_id:
                                self.session_to_pool.pop(session_id, None)
                                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in pool cleanup: {str(e)}", exc_info=True)
    
    def get_or_create_pool_for_session(self, session_id: str) -> 'ConnectionPool':
        """
        Get or create a connection pool for a session
        
        Args:
            session_id: Session ID
            
        Returns:
            ConnectionPool instance
        """
        # Check if session already has a pool
        if session_id in self.session_to_pool:
            pool_id = self.session_to_pool[session_id]
            return self.pools[pool_id]
            
        # Find the least used pool that has space
        target_pool = None
        min_usage = float('inf')
        
        for pool_id, pool in self.pools.items():
            usage = self.pool_usage.get(pool_id, 0)
            if usage < min_usage and pool.connection_count < self.max_connections_per_pool:
                min_usage = usage
                target_pool = pool
                
        # Create a new pool if needed and allowed
        if target_pool is None and len(self.pools) < self.max_pools:
            pool_id = str(uuid.uuid4())
            target_pool = ConnectionPool(pool_id)
            self.pools[pool_id] = target_pool
            self.pool_usage[pool_id] = 0
            logger.info(f"Created new connection pool: {pool_id}")
            
        # If still no pool, use the least used pool (even if full)
        if target_pool is None:
            pool_id, usage = min(self.pool_usage.items(), key=lambda x: x[1])
            target_pool = self.pools[pool_id]
            
        # Update mapping and usage
        self.session_to_pool[session_id] = target_pool.pool_id
        self.pool_usage[target_pool.pool_id] += 1
        
        return target_pool
        
    def register_client(self, client_id: str, session_id: str) -> None:
        """
        Register a client to a session's pool
        
        Args:
            client_id: Client ID
            session_id: Session ID
        """
        if session_id in self.session_to_pool:
            pool_id = self.session_to_pool[session_id]
            self.client_to_pool[client_id] = pool_id
            
    def get_pool_for_client(self, client_id: str) -> Optional['ConnectionPool']:
        """
        Get the connection pool for a client
        
        Args:
            client_id: Client ID
            
        Returns:
            ConnectionPool instance or None if not found
        """
        if client_id in self.client_to_pool:
            pool_id = self.client_to_pool[client_id]
            return self.pools.get(pool_id)
        return None
        
    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about connection pools
        
        Returns:
            Dictionary of pool statistics
        """
        return {
            "total_pools": len(self.pools),
            "total_clients": len(self.client_to_pool),
            "total_sessions": len(self.session_to_pool),
            "pools": [
                {
                    "pool_id": pool_id,
                    "usage": self.pool_usage.get(pool_id, 0),
                    "connections": pool.connection_count,
                    "last_activity": pool.last_activity
                }
                for pool_id, pool in self.pools.items()
            ]
        }


class ConnectionPool:
    """Manages a pool of WebSocket connections for efficient communication"""
    
    def __init__(self, pool_id: str):
        """
        Initialize a connection pool
        
        Args:
            pool_id: Pool ID
        """
        self.pool_id = pool_id
        self.connections: Dict[str, Tuple[Any, Set[str]]] = {}  # client_id -> (websocket, subscriptions)
        self.topic_subscribers: Dict[str, Set[str]] = {}  # topic -> {client_ids}
        self.connection_count = 0
        self.last_activity = time.time()
        self.executor = ThreadPoolExecutor(max_workers=10)
        self.message_queue: asyncio.Queue = asyncio.Queue()
        self.processing_task = None
        
    async def start(self) -> None:
        """Start the connection pool and background tasks"""
        self.processing_task = asyncio.create_task(self._process_messages())
        
    async def stop(self) -> None:
        """Stop the connection pool and background tasks"""
        if self.processing_task:
            self.processing_task.cancel()
            try:
                await self.processing_task
            except asyncio.CancelledError:
                pass
                
        # Close all connections
        for websocket, _ in self.connections.values():
            try:
                await websocket.close()
            except Exception:
                pass
                
        # Shutdown executor
        self.executor.shutdown(wait=False)
        
    async def _process_messages(self) -> None:
        """Process messages from the queue"""
        while True:
            try:
                message, topic, exclude = await self.message_queue.get()
                await self._send_to_subscribers(message, topic, exclude)
                self.message_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error processing message: {str(e)}", exc_info=True)
                
    async def _send_to_subscribers(self, message: Any, topic: str, exclude: Optional[str] = None) -> None:
        """
        Send a message to all subscribers of a topic
        
        Args:
            message: Message to send
            topic: Topic name
            exclude: Optional client ID to exclude
        """
        if topic not in self.topic_subscribers:
            return
            
        # Get subscribers and filter out excluded client
        subscribers = self.topic_subscribers[topic]
        if exclude:
            subscribers = {client_id for client_id in subscribers if client_id != exclude}
            
        # Send to all subscribers
        send_tasks = []
        for client_id in subscribers:
            if client_id in self.connections:
                websocket, _ = self.connections[client_id]
                try:
                    send_tasks.append(websocket.send(message))
                except Exception as e:
                    logger.error(f"Error sending to client {client_id}: {str(e)}")
                    
        if send_tasks:
            await asyncio.gather(*send_tasks, return_exceptions=True)
            
    def add_connection(self, client_id: str, websocket: Any) -> None:
        """
        Add a connection to the pool
        
        Args:
            client_id: Client ID
            websocket: WebSocket connection
        """
        self.connections[client_id] = (websocket, set())
        self.connection_count += 1
        self.last_activity = time.time()
        
    def remove_connection(self, client_id: str) -> None:
        """
        Remove a connection from the pool
        
        Args:
            client_id: Client ID
        """
        if client_id in self.connections:
            _, subscriptions = self.connections.pop(client_id)
            self.connection_count -= 1
            self.last_activity = time.time()
            
            # Remove from all subscribed topics
            for topic in subscriptions:
                if topic in self.topic_subscribers:
                    self.topic_subscribers[topic].discard(client_id)
                    
                    # Clean up empty topic
                    if not self.topic_subscribers[topic]:
                        del self.topic_subscribers[topic]
                        
    def subscribe(self, client_id: str, topic: str) -> None:
        """
        Subscribe a client to a topic
        
        Args:
            client_id: Client ID
            topic: Topic to subscribe to
        """
        if client_id not in self.connections:
            return
            
        # Add topic to client's subscriptions
        _, subscriptions = self.connections[client_id]
        subscriptions.add(topic)
        
        # Add client to topic subscribers
        if topic not in self.topic_subscribers:
            self.topic_subscribers[topic] = set()
        self.topic_subscribers[topic].add(client_id)
        
        self.last_activity = time.time()
        
    def unsubscribe(self, client_id: str, topic: str) -> None:
        """
        Unsubscribe a client from a topic
        
        Args:
            client_id: Client ID
            topic: Topic to unsubscribe from
        """
        if client_id not in self.connections:
            return
            
        # Remove topic from client's subscriptions
        _, subscriptions = self.connections[client_id]
        subscriptions.discard(topic)
        
        # Remove client from topic subscribers
        if topic in self.topic_subscribers:
            self.topic_subscribers[topic].discard(client_id)
            
            # Clean up empty topic
            if not self.topic_subscribers[topic]:
                del self.topic_subscribers[topic]
                
        self.last_activity = time.time()
        
    async def broadcast(self, message: Any, topic: str, exclude: Optional[str] = None) -> None:
        """
        Broadcast a message to all subscribers of a topic
        
        Args:
            message: Message to send
            topic: Topic name
            exclude: Optional client ID to exclude
        """
        # Update activity timestamp
        self.last_activity = time.time()
        
        # Queue the message for processing
        await self.message_queue.put((message, topic, exclude))
        
    async def send_to_client(self, client_id: str, message: Any) -> bool:
        """
        Send a message to a specific client
        
        Args:
            client_id: Client ID
            message: Message to send
            
        Returns:
            True if successful, False otherwise
        """
        if client_id not in self.connections:
            return False
            
        websocket, _ = self.connections[client_id]
        try:
            await websocket.send(message)
            self.last_activity = time.time()
            return True
        except Exception as e:
            logger.error(f"Error sending to client {client_id}: {str(e)}")
            return False
            
    def get_topic_subscribers(self, topic: str) -> Set[str]:
        """
        Get all subscribers for a topic
        
        Args:
            topic: Topic name
            
        Returns:
            Set of client IDs
        """
        return self.topic_subscribers.get(topic, set())
        
    def get_client_subscriptions(self, client_id: str) -> Set[str]:
        """
        Get all subscriptions for a client
        
        Args:
            client_id: Client ID
            
        Returns:
            Set of topic names
        """
        if client_id in self.connections:
            _, subscriptions = self.connections[client_id]
            return subscriptions
        return set()