"""
Data Pipeline - Message Queue Integration

Implements RabbitMQ-based data pipeline for metric ingestion.
"""

from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, asdict
from datetime import datetime
import asyncio
import json
import logging

import pika
from pika.adapters.asyncio_connection import AsyncioConnection
from pika.exchange_type import ExchangeType

logger = logging.getLogger(__name__)


@dataclass
class MetricMessage:
    """Standardized metric message format"""
    device_id: str
    metric_name: str
    value: Any
    unit: str
    timestamp: str  # ISO format
    source: str  # snmp, modbus, profinet
    tags: Dict[str, Any]
    
    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(asdict(self))
    
    @classmethod
    def from_json(cls, json_str: str) -> 'MetricMessage':
        """Create from JSON string"""
        data = json.loads(json_str)
        return cls(**data)


class MessageQueuePublisher:
    """
    RabbitMQ publisher for metric data
    
    Features:
    - Async publishing
    - Connection retry
    - Message persistence
    - Exchange/queue setup
    """
    
    def __init__(
        self,
        host: str = 'localhost',
        port: int = 5672,
        username: str = 'guest',
        password: str = 'guest',
        exchange: str = 'nethealth.metrics',
        exchange_type: str = 'topic'
    ):
        """
        Initialize publisher
        
        Args:
            host: RabbitMQ host
            port: RabbitMQ port
            username: RabbitMQ username
            password: RabbitMQ password
            exchange: Exchange name
            exchange_type: Exchange type (topic, direct, fanout)
        """
        self.host = host
        self.port = port
        self.credentials = pika.PlainCredentials(username, password)
        self.exchange = exchange
        self.exchange_type = exchange_type
        
        self.connection: Optional[pika.BlockingConnection] = None
        self.channel: Optional[pika.channel.Channel] = None
    
    def connect(self):
        """Establish connection to RabbitMQ"""
        try:
            parameters = pika.ConnectionParameters(
                host=self.host,
                port=self.port,
                credentials=self.credentials,
                heartbeat=600,
                blocked_connection_timeout=300
            )
            
            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()
            
            # Declare exchange
            self.channel.exchange_declare(
                exchange=self.exchange,
                exchange_type=self.exchange_type,
                durable=True
            )
            
            logger.info(f"Connected to RabbitMQ at {self.host}:{self.port}")
            
        except Exception as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}")
            raise
    
    def disconnect(self):
        """Close connection"""
        if self.connection and not self.connection.is_closed:
            self.connection.close()
            logger.info("Disconnected from RabbitMQ")
    
    def publish(
        self,
        message: MetricMessage,
        routing_key: Optional[str] = None
    ) -> bool:
        """
        Publish metric message
        
        Args:
            message: Metric message
            routing_key: Routing key (default: source.device_id)
        
        Returns:
            True if published successfully
        """
        if not self.channel:
            logger.error("Not connected to RabbitMQ")
            return False
        
        try:
            # Default routing key: source.device_id
            if not routing_key:
                routing_key = f"{message.source}.{message.device_id}"
            
            # Publish with persistence
            self.channel.basic_publish(
                exchange=self.exchange,
                routing_key=routing_key,
                body=message.to_json(),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Persistent
                    content_type='application/json',
                    timestamp=int(datetime.utcnow().timestamp())
                )
            )
            
            logger.debug(f"Published metric: {message.metric_name} from {message.device_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error publishing message: {e}")
            return False
    
    def publish_batch(self, messages: List[MetricMessage]) -> int:
        """
        Publish multiple messages
        
        Args:
            messages: List of metric messages
        
        Returns:
            Number of messages published successfully
        """
        success_count = 0
        
        for message in messages:
            if self.publish(message):
                success_count += 1
        
        return success_count


class MessageQueueConsumer:
    """
    RabbitMQ consumer for metric data
    
    Features:
    - Async consumption
    - Auto-acknowledgment
    - Message batching
    - Error handling
    """
    
    def __init__(
        self,
        host: str = 'localhost',
        port: int = 5672,
        username: str = 'guest',
        password: str = 'guest',
        exchange: str = 'nethealth.metrics',
        queue: str = 'nethealth.metrics.processing',
        routing_keys: List[str] = None
    ):
        """
        Initialize consumer
        
        Args:
            host: RabbitMQ host
            port: RabbitMQ port
            username: RabbitMQ username
            password: RabbitMQ password
            exchange: Exchange name
            queue: Queue name
            routing_keys: List of routing keys to bind (default: ['#'])
        """
        self.host = host
        self.port = port
        self.credentials = pika.PlainCredentials(username, password)
        self.exchange = exchange
        self.queue = queue
        self.routing_keys = routing_keys or ['#']  # All messages
        
        self.connection: Optional[pika.BlockingConnection] = None
        self.channel: Optional[pika.channel.Channel] = None
        self.callback: Optional[Callable] = None
    
    def connect(self):
        """Establish connection to RabbitMQ"""
        try:
            parameters = pika.ConnectionParameters(
                host=self.host,
                port=self.port,
                credentials=self.credentials,
                heartbeat=600,
                blocked_connection_timeout=300
            )
            
            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()
            
            # Declare queue
            self.channel.queue_declare(
                queue=self.queue,
                durable=True,
                arguments={
                    'x-max-length': 100000,  # Max queue length
                    'x-message-ttl': 86400000,  # 24 hours TTL
                }
            )
            
            # Bind queue to exchange with routing keys
            for routing_key in self.routing_keys:
                self.channel.queue_bind(
                    exchange=self.exchange,
                    queue=self.queue,
                    routing_key=routing_key
                )
            
            # Set QoS (prefetch count)
            self.channel.basic_qos(prefetch_count=10)
            
            logger.info(f"Connected to RabbitMQ queue: {self.queue}")
            
        except Exception as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}")
            raise
    
    def disconnect(self):
        """Close connection"""
        if self.connection and not self.connection.is_closed:
            self.connection.close()
            logger.info("Disconnected from RabbitMQ")
    
    def consume(self, callback: Callable[[MetricMessage], None]):
        """
        Start consuming messages
        
        Args:
            callback: Function to call for each message
        """
        if not self.channel:
            logger.error("Not connected to RabbitMQ")
            return
        
        self.callback = callback
        
        def on_message(ch, method, properties, body):
            try:
                # Parse message
                message = MetricMessage.from_json(body.decode('utf-8'))
                
                # Call callback
                self.callback(message)
                
                # Acknowledge message
                ch.basic_ack(delivery_tag=method.delivery_tag)
                
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                # Reject and requeue
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        
        # Start consuming
        self.channel.basic_consume(
            queue=self.queue,
            on_message_callback=on_message
        )
        
        logger.info(f"Starting to consume from {self.queue}")
        
        try:
            self.channel.start_consuming()
        except KeyboardInterrupt:
            self.channel.stop_consuming()
            logger.info("Stopped consuming")
    
    def stop(self):
        """Stop consuming"""
        if self.channel:
            self.channel.stop_consuming()


class DataPipeline:
    """
    Complete data pipeline orchestrator
    
    Coordinates collectors, message queue, and database storage.
    """
    
    def __init__(
        self,
        publisher: MessageQueuePublisher,
        consumer: MessageQueueConsumer,
        db_manager
    ):
        """
        Initialize data pipeline
        
        Args:
            publisher: Message queue publisher
            consumer: Message queue consumer
            db_manager: Database manager
        """
        self.publisher = publisher
        self.consumer = consumer
        self.db_manager = db_manager
        
        self.collectors = []
        self.running = False
    
    def add_collector(self, collector, collector_type: str):
        """
        Add a data collector
        
        Args:
            collector: Collector instance (SNMP, Modbus, Profinet)
            collector_type: Type identifier
        """
        self.collectors.append((collector, collector_type))
        logger.info(f"Added {collector_type} collector to pipeline")
    
    async def collector_callback(self, device_id: str, metrics: List):
        """
        Callback for collectors to publish metrics
        
        Args:
            device_id: Device ID
            metrics: List of metrics (SNMP/Modbus/Profinet specific)
        """
        messages = []
        
        for metric in metrics:
            # Convert to standardized format
            message = MetricMessage(
                device_id=metric.device_id,
                metric_name=metric.metric_name,
                value=metric.value,
                unit=metric.unit,
                timestamp=metric.timestamp.isoformat(),
                source=metric.tags.get('source', 'unknown'),
                tags=metric.tags
            )
            messages.append(message)
        
        # Publish to queue
        if messages:
            count = self.publisher.publish_batch(messages)
            logger.debug(f"Published {count}/{len(messages)} metrics from {device_id}")
    
    def storage_callback(self, message: MetricMessage):
        """
        Callback for consumer to store metrics in database
        
        Args:
            message: Metric message
        """
        try:
            from src.database.repository import MetricsRepository
            
            with self.db_manager.get_session() as session:
                repo = MetricsRepository(session)
                
                # Convert to database format
                metric_data = {
                    'time': datetime.fromisoformat(message.timestamp),
                    'asset_id': message.device_id,
                    'metric_name': message.metric_name,
                    'value': float(message.value) if isinstance(message.value, (int, float)) else None,
                    'unit': message.unit,
                    'tags': message.tags
                }
                
                # Insert
                repo.insert_batch([metric_data])
                
                logger.debug(f"Stored metric: {message.metric_name} from {message.device_id}")
                
        except Exception as e:
            logger.error(f"Error storing metric: {e}")
    
    async def start(self):
        """Start the data pipeline"""
        self.running = True
        logger.info("Starting data pipeline")
        
        # Connect publisher and consumer
        self.publisher.connect()
        self.consumer.connect()
        
        # Start collectors
        collector_tasks = []
        for collector, collector_type in self.collectors:
            task = asyncio.create_task(
                collector.start_polling(callback=self.collector_callback)
            )
            collector_tasks.append(task)
            logger.info(f"Started {collector_type} collector")
        
        # Start consumer in separate thread
        import threading
        consumer_thread = threading.Thread(
            target=self.consumer.consume,
            args=(self.storage_callback,),
            daemon=True
        )
        consumer_thread.start()
        logger.info("Started message consumer")
        
        # Wait for collectors
        await asyncio.gather(*collector_tasks)
    
    async def stop(self):
        """Stop the data pipeline"""
        self.running = False
        logger.info("Stopping data pipeline")
        
        # Stop collectors
        for collector, _ in self.collectors:
            if hasattr(collector, 'stop_polling'):
                collector.stop_polling()
        
        # Stop consumer
        self.consumer.stop()
        
        # Disconnect
        self.publisher.disconnect()
        self.consumer.disconnect()
        
        logger.info("Data pipeline stopped")
