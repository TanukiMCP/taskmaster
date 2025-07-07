"""
Dependency injection container for the Taskmaster application.

Provides centralized dependency management with proper lifecycle control,
configuration injection, and service registration for better testability
and maintainability.
"""

import logging
import importlib
import inspect
import os
from pathlib import Path
from typing import Dict, Any, Optional, TypeVar, Type, Callable, Union
from abc import ABC, abstractmethod
from .config import Config, get_config
from .session_manager import SessionManager
from .validation_engine import ValidationEngine

from .command_handler import TaskmasterCommandHandler
from .workflow_state_machine import WorkflowStateMachine
from .async_session_persistence import AsyncSessionPersistence
from .exceptions import ConfigurationError, ErrorCode

logger = logging.getLogger(__name__)

T = TypeVar('T')


class ServiceLifecycle:
 """Enumeration of service lifecycle types."""
 SINGLETON = "singleton"
 TRANSIENT = "transient"
 SCOPED = "scoped"


class ServiceRegistration:
    """Represents a service registration in the container."""
    
    def __init__(
        self,
        service_type: Type,
        factory: Callable[..., Any],
        lifecycle: str = ServiceLifecycle.SINGLETON,
        dependencies: Optional[Dict[str, str]] = None
    ):
        self.service_type = service_type
        self.factory = factory
        self.lifecycle = lifecycle
        self.dependencies = dependencies or {}
        self.instance: Optional[Any] = None


class IServiceContainer(ABC):
    """Interface for service containers."""
    
    @abstractmethod
    def register(
        self,
        service_type: Type[T],
        factory: Callable[..., T],
        lifecycle: str = ServiceLifecycle.SINGLETON
    ) -> None:
        """Register a service with the container."""
        pass
    
    @abstractmethod
    def resolve(self, service_type: Type[T]) -> T:
        """Resolve a service from the container."""
        pass
    
    @abstractmethod
    def is_registered(self, service_type: Type[T]) -> bool:
        """Check if a service is registered."""
        pass


class TaskmasterContainer(IServiceContainer):
    """
    Dependency injection container for managing Taskmaster services.
    
    Provides centralized service registration, resolution, and lifecycle management
    with support for singleton, transient, and scoped service lifetimes.
    """
    
    def __init__(self, config: Optional[Config] = None):
        """
        Initialize the container with optional configuration.
        
        Args:
            config: Configuration instance. If None, uses default config.
        """
        self._services: Dict[Type, ServiceRegistration] = {}
        self._config = config or get_config()
        self._scope_instances: Dict[str, Dict[Type, Any]] = {}
        self._current_scope: Optional[str] = None
        
        # Register core services
        self._register_lightweight_core_services()
        
        logger.info("TaskmasterContainer initialized")
    
    def _register_lightweight_core_services(self) -> None:
        """Register core Taskmaster services with ultra-lightweight lazy initialization."""
        try:
            # Register configuration
            self.register_instance(Config, self._config)
            
            # SMITHERY OPTIMIZATION: Register all services with lazy factories
            # This avoids any heavy initialization during container creation
            
            # Register async session persistence with ultra-lazy creation
            self.register(
                AsyncSessionPersistence,
                lambda: AsyncSessionPersistence(
                    storage_directory=Path(self._config.get_state_directory()),
                    backup_count=self._config.get('session_backup_count', 5)
                ),
                ServiceLifecycle.SINGLETON
            )
            
            # Register workflow state machine with ultra-lazy creation
            self.register(
                WorkflowStateMachine,
                lambda: WorkflowStateMachine(),
                ServiceLifecycle.SINGLETON
            )
            
            # Register session manager with ultra-lazy dependencies
            self.register(
                SessionManager,
                lambda: SessionManager(
                    state_dir=self._config.get_state_directory(),
                    persistence=self.resolve(AsyncSessionPersistence),
                    workflow_state_machine=self.resolve(WorkflowStateMachine)
                ),
                ServiceLifecycle.SINGLETON
            )
            
            # Register validation engine with ultra-lazy creation
            self.register(
                ValidationEngine,
                lambda: ValidationEngine(),
                ServiceLifecycle.SINGLETON
            )
            
            # Register main command handler with ultra-lazy dependencies
            self.register(
                TaskmasterCommandHandler,
                lambda: TaskmasterCommandHandler(
                    session_manager=self.resolve(SessionManager),
                    validation_engine=self.resolve(ValidationEngine)
                ),
                ServiceLifecycle.SINGLETON
            )
            
            # SMITHERY OPTIMIZATION: Mark command handlers as not registered
            # This ensures they're only loaded when the command handler is first resolved
            self._command_handlers_registered = False
            self._session_cleanup_registered = False
            
            logger.info("Core services registered with ultra-lightweight lazy initialization")
            
        except Exception as e:
            logger.error(f"Failed to register core services: {e}")
            raise ConfigurationError(
                message="Failed to register core services",
                error_code=ErrorCode.CONFIG_INVALID,
                cause=e
            )
    
    def _register_command_handlers_lazy(self) -> None:
        """Register command handlers lazily to avoid startup timeout."""
        # This method defers the actual registration until the first resolution
        # to avoid heavy initialization during container creation
        self._command_handlers_registered = False
    
    def _register_session_cleanup_service_lazy(self) -> None:
        """Register session cleanup service lazily."""
        # This method defers the actual registration until needed
        self._session_cleanup_registered = False
    
    def _ensure_command_handlers_registered(self) -> None:
        """Ensure command handlers are registered when needed."""
        if hasattr(self, '_command_handlers_registered') and not self._command_handlers_registered:
            try:
                self._register_command_handlers()
                self._command_handlers_registered = True
            except Exception as e:
                logger.error(f"Failed to register command handlers lazily: {e}")
                # Continue without command handlers for basic functionality
    
    def _register_command_handlers(self) -> None:
        """Register all command handlers with the main command handler."""
        try:
            # Import command handler classes from the main command_handler module
            from .command_handler import (
                CreateSessionHandler, DeclareCapabilitiesHandler, DiscoverCapabilitiesHandler,
                CreateTasklistHandler, MapCapabilitiesHandler, ExecuteNextHandler, MarkCompleteHandler,
                GetStatusHandler, CollaborationRequestHandler, InitializeWorldModelHandler,
                CreateHierarchicalPlanHandler, InitiateAdversarialReviewHandler,
                RecordHostGroundingHandler, UpdateWorldModelHandler, StaticAnalysisHandler,
                RecordAdversarialFindingsHandler, RecordTestResultsHandler, AdvanceHierarchicalStepHandler
            )
            
            # Get dependencies
            main_handler = self.resolve(TaskmasterCommandHandler)
            session_manager = self.resolve(SessionManager)
            validation_engine = self.resolve(ValidationEngine)
            
            # Register all command handlers that are defined in command_handler.py
            handlers = {
                "create_session": CreateSessionHandler(session_manager, validation_engine),
                "declare_capabilities": DeclareCapabilitiesHandler(session_manager, validation_engine),
                "discover_capabilities": DiscoverCapabilitiesHandler(session_manager, validation_engine),
                "create_tasklist": CreateTasklistHandler(session_manager, validation_engine),
                "map_capabilities": MapCapabilitiesHandler(session_manager, validation_engine),
                "execute_next": ExecuteNextHandler(session_manager, validation_engine),
                "mark_complete": MarkCompleteHandler(session_manager, validation_engine),
                "get_status": GetStatusHandler(session_manager, validation_engine),
                "collaboration_request": CollaborationRequestHandler(session_manager, validation_engine),
                "initialize_world_model": InitializeWorldModelHandler(session_manager, validation_engine),
                "create_hierarchical_plan": CreateHierarchicalPlanHandler(session_manager, validation_engine),
                "initiate_adversarial_review": InitiateAdversarialReviewHandler(session_manager, validation_engine),
                "record_host_grounding": RecordHostGroundingHandler(session_manager, validation_engine),
                "update_world_model": UpdateWorldModelHandler(session_manager, validation_engine),
                "static_analysis": StaticAnalysisHandler(session_manager, validation_engine),
                "record_adversarial_findings": RecordAdversarialFindingsHandler(session_manager, validation_engine),
                "record_test_results": RecordTestResultsHandler(session_manager, validation_engine),
                "advance_hierarchical_step": AdvanceHierarchicalStepHandler(session_manager, validation_engine),
            }
            
            # Add handlers to main command handler
            for action, handler in handlers.items():
                main_handler.add_handler(action, handler)
            
            logger.info(f"Registered {len(handlers)} command handlers lazily")
            
        except Exception as e:
            logger.error(f"Failed to register command handlers: {e}")
            raise ConfigurationError(
                message="Failed to register command handlers",
                error_code=ErrorCode.CONFIG_INVALID,
                cause=e
            )
    
    def _register_session_cleanup_service(self) -> None:
        """Register session cleanup service."""
        try:
            from .session_cleanup_service import SessionCleanupService
            
            self.register(
                SessionCleanupService,
                lambda: SessionCleanupService(
                    persistence=self.resolve(AsyncSessionPersistence),
                    config=self._config
                ),
                ServiceLifecycle.SINGLETON
            )
            
            logger.info("Session cleanup service registered")
            
        except ImportError:
            # Session cleanup service doesn't exist yet, we'll create it later
            logger.debug("Session cleanup service not found, will be created later")
        except Exception as e:
            logger.error(f"Failed to register session cleanup service: {e}")
    
    def register(
        self,
        service_type: Type[T],
        factory: Callable[..., T],
        lifecycle: str = ServiceLifecycle.SINGLETON,
        dependencies: Optional[Dict[str, str]] = None
    ) -> None:
        """
        Register a service with the container.
        
        Args:
            service_type: The type of service to register
            factory: Factory function to create the service
            lifecycle: Service lifecycle (singleton, transient, scoped)
            dependencies: Optional dependency mapping
        """
        if service_type in self._services:
            logger.warning(f"Service {service_type.__name__} is already registered. Overriding.")
        
        registration = ServiceRegistration(
            service_type=service_type,
            factory=factory,
            lifecycle=lifecycle,
            dependencies=dependencies
        )
        
        self._services[service_type] = registration
        logger.debug(f"Registered service: {service_type.__name__} with {lifecycle} lifecycle")
    
    def register_instance(self, service_type: Type[T], instance: T) -> None:
        """
        Register a service instance directly.
        
        Args:
            service_type: The type of service
            instance: The service instance
        """
        registration = ServiceRegistration(
            service_type=service_type,
            factory=lambda: instance,
            lifecycle=ServiceLifecycle.SINGLETON
        )
        registration.instance = instance
        
        self._services[service_type] = registration
        logger.debug(f"Registered service instance: {service_type.__name__}")
    
    def resolve(self, service_type: Type[T]) -> T:
        """
        Resolve a service from the container.
        
        Args:
            service_type: The type of service to resolve
        
        Returns:
            The resolved service instance
        
        Raises:
            ConfigurationError: If the service is not registered
        """
        # Ensure command handlers are registered when resolving TaskmasterCommandHandler
        if service_type.__name__ == 'TaskmasterCommandHandler':
            self._ensure_command_handlers_registered()
        
        if service_type not in self._services:
            raise ConfigurationError(
                message=f"Service {service_type.__name__} is not registered",
                error_code=ErrorCode.CONFIG_INVALID,
                details={"service_type": service_type.__name__}
            )
        
        registration = self._services[service_type]
        
        try:
            if registration.lifecycle == ServiceLifecycle.SINGLETON:
                return self._resolve_singleton(registration)
            elif registration.lifecycle == ServiceLifecycle.TRANSIENT:
                return self._resolve_transient(registration)
            elif registration.lifecycle == ServiceLifecycle.SCOPED:
                return self._resolve_scoped(registration)
            else:
                raise ConfigurationError(
                    message=f"Unknown service lifecycle: {registration.lifecycle}",
                    error_code=ErrorCode.CONFIG_INVALID,
                    details={"lifecycle": registration.lifecycle}
                )
        
        except Exception as e:
            logger.error(f"Failed to resolve service {service_type.__name__}: {e}")
            raise ConfigurationError(
                message=f"Failed to resolve service {service_type.__name__}",
                error_code=ErrorCode.CONFIG_INVALID,
                details={"service_type": service_type.__name__},
                cause=e
            )
    
    def _resolve_singleton(self, registration: ServiceRegistration) -> Any:
        """Resolve a singleton service."""
        if registration.instance is None:
            registration.instance = registration.factory()
            logger.debug(f"Created singleton instance: {registration.service_type.__name__}")
        
        return registration.instance
    
    def _resolve_transient(self, registration: ServiceRegistration) -> Any:
        """Resolve a transient service (new instance each time)."""
        instance = registration.factory()
        logger.debug(f"Created transient instance: {registration.service_type.__name__}")
        return instance
    
    def _resolve_scoped(self, registration: ServiceRegistration) -> Any:
        """Resolve a scoped service (one instance per scope)."""
        if self._current_scope is None:
            raise ConfigurationError(
                message="No active scope for scoped service resolution",
                error_code=ErrorCode.CONFIG_INVALID,
                details={"service_type": registration.service_type.__name__}
            )
        
        scope_instances = self._scope_instances.get(self._current_scope, {})
        
        if registration.service_type not in scope_instances:
            instance = registration.factory()
            scope_instances[registration.service_type] = instance
            self._scope_instances[self._current_scope] = scope_instances
            logger.debug(f"Created scoped instance: {registration.service_type.__name__}")
        
        return scope_instances[registration.service_type]
    
    def is_registered(self, service_type: Type[T]) -> bool:
        """
        Check if a service is registered.
        
        Args:
            service_type: The type of service to check
        
        Returns:
            True if the service is registered, False otherwise
        """
        return service_type in self._services
    
    def create_scope(self, scope_id: str) -> 'ServiceScope':
        """
        Create a new service scope.
        
        Args:
            scope_id: Unique identifier for the scope
        
        Returns:
            ServiceScope context manager
        """
        return ServiceScope(self, scope_id)
    
    def _enter_scope(self, scope_id: str) -> None:
        """Enter a service scope."""
        self._current_scope = scope_id
        if scope_id not in self._scope_instances:
            self._scope_instances[scope_id] = {}
        logger.debug(f"Entered scope: {scope_id}")
    
    def _exit_scope(self, scope_id: str) -> None:
        """Exit a service scope and clean up scoped instances."""
        if scope_id in self._scope_instances:
            # Dispose of scoped instances if they have a dispose method
            for instance in self._scope_instances[scope_id].values():
                if hasattr(instance, 'dispose'):
                    try:
                        instance.dispose()
                    except Exception as e:
                        logger.warning(f"Error disposing scoped instance: {e}")
            
            del self._scope_instances[scope_id]
        
        if self._current_scope == scope_id:
            self._current_scope = None
        
        logger.debug(f"Exited scope: {scope_id}")
    
    def get_registered_services(self) -> Dict[str, Dict[str, Any]]:
        """
        Get information about all registered services.
        
        Returns:
            Dictionary containing service information
        """
        return {
            service_type.__name__: {
                "type": service_type.__name__,
                "lifecycle": registration.lifecycle,
                "has_instance": registration.instance is not None,
                "dependencies": registration.dependencies
            }
            for service_type, registration in self._services.items()
        }
    
    def dispose(self) -> None:
        """Dispose of the container and clean up resources."""
        # Dispose of all singleton instances
        for registration in self._services.values():
            if registration.instance and hasattr(registration.instance, 'dispose'):
                try:
                    registration.instance.dispose()
                except Exception as e:
                    logger.warning(f"Error disposing singleton instance: {e}")
        
        # Clear all scopes
        for scope_id in list(self._scope_instances.keys()):
            self._exit_scope(scope_id)
        
        self._services.clear()
        logger.info("TaskmasterContainer disposed")


class ServiceScope:
    """Context manager for service scopes."""
    
    def __init__(self, container: TaskmasterContainer, scope_id: str):
        self.container = container
        self.scope_id = scope_id
    
    def __enter__(self) -> 'ServiceScope':
        self.container._enter_scope(self.scope_id)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.container._exit_scope(self.scope_id)


class ContainerBuilder:
    """Builder for creating and configuring TaskmasterContainer instances."""
    
    def __init__(self):
        self._config: Optional[Config] = None
        self._additional_services: Dict[Type, ServiceRegistration] = {}
    
    def with_config(self, config: Config) -> 'ContainerBuilder':
        """
        Configure the container with a specific configuration.
        
        Args:
            config: Configuration instance
        
        Returns:
            Self for method chaining
        """
        self._config = config
        return self
    
    def register_service(
        self,
        service_type: Type[T],
        factory: Callable[..., T],
        lifecycle: str = ServiceLifecycle.SINGLETON
    ) -> 'ContainerBuilder':
        """
        Register an additional service.
        
        Args:
            service_type: The type of service to register
            factory: Factory function to create the service
            lifecycle: Service lifecycle
        
        Returns:
            Self for method chaining
        """
        registration = ServiceRegistration(
            service_type=service_type,
            factory=factory,
            lifecycle=lifecycle
        )
        self._additional_services[service_type] = registration
        return self
    
    def build(self) -> TaskmasterContainer:
        """
        Build the container with the configured services.
        
        Returns:
            Configured TaskmasterContainer instance
        """
        container = TaskmasterContainer(self._config)
        
        # Register additional services
        for service_type, registration in self._additional_services.items():
            container.register(
                service_type,
                registration.factory,
                registration.lifecycle,
                registration.dependencies
            )
        
        logger.info(f"Built container with {len(container._services)} services")
        return container


# Global container instance (can be overridden for testing)
_global_container: Optional[TaskmasterContainer] = None


def get_container() -> TaskmasterContainer:
    """
    Get the global container instance.
    
    Returns:
        The global TaskmasterContainer instance
    """
    global _global_container
    if _global_container is None:
        _global_container = TaskmasterContainer()
    return _global_container


def set_container(container: TaskmasterContainer) -> None:
    """
    Set the global container instance.
    
    Args:
        container: The container instance to set as global
    """
    global _global_container
    _global_container = container


def create_container_builder() -> ContainerBuilder:
    """
    Create a new container builder.
    
    Returns:
        ContainerBuilder instance
    """
    return ContainerBuilder() 