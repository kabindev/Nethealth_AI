"""
Database Connection Manager

Handles PostgreSQL/TimescaleDB connections with connection pooling.
"""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import QueuePool
from contextlib import contextmanager
import os
from typing import Optional
import logging

from src.database.models import Base

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Manages database connections and sessions
    
    Features:
    - Connection pooling
    - Session management
    - Automatic reconnection
    - Health checks
    """
    
    def __init__(
        self,
        database_url: Optional[str] = None,
        pool_size: int = 10,
        max_overflow: int = 20,
        pool_timeout: int = 30,
        pool_recycle: int = 3600
    ):
        """
        Initialize database manager
        
        Args:
            database_url: Connection URL
            pool_size: Number of connections to maintain
            max_overflow: Max connections beyond pool_size
            pool_timeout: Timeout for getting connection from pool
            pool_recycle: Recycle connections after this many seconds
        """
        # Get database URL from environment or parameter
        # Default to SQLite for local development without Docker
        self.database_url = database_url or os.getenv(
            'DATABASE_URL',
            'sqlite:///nethealth.db'
        )
        
        is_sqlite = self.database_url.startswith('sqlite')
        
        # Configure engine based on dialect
        engine_args = {
            'echo': False,
            'future': True
        }
        
        if not is_sqlite:
            # PostgreSQL specific settings
            engine_args.update({
                'poolclass': QueuePool,
                'pool_size': pool_size,
                'max_overflow': max_overflow,
                'pool_timeout': pool_timeout,
                'pool_recycle': pool_recycle,
            })
        else:
            # SQLite specific settings (multithreading support check needed usually, but basic is fine)
            from sqlalchemy.pool import StaticPool
            if ':memory:' in self.database_url:
                engine_args.update({
                    'poolclass': StaticPool,
                    'connect_args': {'check_same_thread': False}
                })
            else:
                # File-based SQLite
                # Using standard pool but enabling foreign keys
                pass

        # Create engine
        self.engine = create_engine(self.database_url, **engine_args)
        
        # Create session factory
        self.session_factory = sessionmaker(
            bind=self.engine,
            autocommit=False,
            autoflush=False
        )
        
        # Thread-safe session
        self.Session = scoped_session(self.session_factory)
        
        # Setup event listeners
        self._setup_event_listeners(is_sqlite)
        
        logger.info(f"Database manager initialized (SQLite={is_sqlite})")
    
    def _setup_event_listeners(self, is_sqlite: bool = False):
        """Setup SQLAlchemy event listeners"""
        
        @event.listens_for(self.engine, "connect")
        def receive_connect(dbapi_conn, connection_record):
            """On connection"""
            cursor = dbapi_conn.cursor()
            if is_sqlite:
                # Enable foreign keys for SQLite
                cursor.execute("PRAGMA foreign_keys=ON")
            else:
                # Set timezone to UTC for Postgres
                cursor.execute("SET timezone='UTC'")
            cursor.close()
        
        @event.listens_for(self.engine, "checkout")
        def receive_checkout(dbapi_conn, connection_record, connection_proxy):
            """On checkout, verify connection is alive"""
            cursor = dbapi_conn.cursor()
            try:
                cursor.execute("SELECT 1")
            except Exception:
                # Connection is dead, raise error to get new connection
                raise
            finally:
                cursor.close()
    
    def create_tables(self):
        """Create all tables if they don't exist"""
        try:
            Base.metadata.create_all(self.engine)
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Error creating tables: {e}")
            raise
    
    def drop_tables(self):
        """Drop all tables (use with caution!)"""
        try:
            Base.metadata.drop_all(self.engine)
            logger.warning("All database tables dropped")
        except Exception as e:
            logger.error(f"Error dropping tables: {e}")
            raise
    
    @contextmanager
    def get_session(self):
        """
        Context manager for database sessions
        
        Usage:
            with db_manager.get_session() as session:
                session.query(Asset).all()
        """
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()
    
    def health_check(self) -> bool:
        """
        Check database connectivity
        
        Returns:
            True if database is accessible, False otherwise
        """
        try:
            from sqlalchemy import text
            with self.get_session() as session:
                session.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False
    
    def get_connection_info(self) -> dict:
        """Get connection pool information"""
        pool = self.engine.pool
        return {
            'pool_size': pool.size(),
            'checked_out': pool.checkedout(),
            'overflow': pool.overflow(),
            'checked_in': pool.checkedin()
        }
    
    def close(self):
        """Close all connections and dispose engine"""
        self.Session.remove()
        self.engine.dispose()
        logger.info("Database connections closed")


# Global database manager instance
_db_manager: Optional[DatabaseManager] = None


def get_db_manager() -> DatabaseManager:
    """
    Get global database manager instance
    
    Returns:
        DatabaseManager instance
    """
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


def init_database(database_url: Optional[str] = None, create_tables: bool = True):
    """
    Initialize database
    
    Args:
        database_url: PostgreSQL connection URL
        create_tables: Whether to create tables
    """
    global _db_manager
    _db_manager = DatabaseManager(database_url=database_url)
    
    if create_tables:
        _db_manager.create_tables()
    
    logger.info("Database initialized successfully")
    return _db_manager
