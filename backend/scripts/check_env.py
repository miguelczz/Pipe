#!/usr/bin/env python3
"""
Script para verificar la configuración del entorno.
Útil para diagnosticar problemas de configuración.
"""
import os
import sys
from pathlib import Path

# Agregar el directorio backend al path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

def check_env_file():
    """Verifica si existe el archivo .env"""
    env_file = backend_dir / ".env"
    if env_file.exists():
        print("✓ Archivo .env encontrado")
        return True
    else:
        print("✗ Archivo .env NO encontrado en backend/")
        print("  Crea un archivo .env basado en .env.example")
        return False

def check_required_vars():
    """Verifica variables de entorno requeridas"""
    errors = []
    warnings = []
    
    try:
        from src.settings import settings
    except Exception as e:
        errors.append(f"Error al cargar configuración: {e}")
        return errors, warnings
    
    # Usar el método de validación de settings
    validation_errors = settings.validate_required()
    
    # Variables críticas
    if not settings.openai_api_key:
        if settings.is_production:
            errors.append("OPENAI_API_KEY no está configurada (requerida en producción)")
        else:
            warnings.append("OPENAI_API_KEY no está configurada (recomendada)")
    else:
        print("✓ OPENAI_API_KEY configurada")
    
    if not settings.qdrant_url:
        if settings.is_production:
            errors.append("QDRANT_URL no está configurada (requerida en producción)")
        else:
            warnings.append("QDRANT_URL no está configurada (recomendada)")
    else:
        print(f"✓ QDRANT_URL: {settings.qdrant_url}")
    
    # Base de datos
    try:
        db_url = settings.sqlalchemy_url
        print(f"✓ Configuración de base de datos: {db_url.split('@')[-1] if '@' in db_url else 'configurada'}")
    except Exception as e:
        errors.append(f"Error en configuración de base de datos: {e}")
    
    # Redis
    if not settings.redis_url:
        warnings.append("REDIS_URL no está configurada (el caché puede no funcionar)")
    else:
        print(f"✓ REDIS_URL: {settings.redis_url}")
    
    # Entorno
    print(f"✓ Entorno: {settings.app_env}")
    
    if settings.app_env == "production" and not settings.secret_key:
        warnings.append("SECRET_KEY no está configurada (requerido en producción)")
    elif settings.secret_key:
        print("✓ SECRET_KEY configurada")
    
    return errors, warnings

def check_database_connection():
    """Intenta conectar a la base de datos"""
    try:
        from src.models.database import get_engine
        engine = get_engine()
        with engine.connect() as conn:
            from sqlalchemy import text
            conn.execute(text("SELECT 1"))
        print("✓ Conexión a base de datos exitosa")
        return True
    except Exception as e:
        print(f"✗ No se pudo conectar a la base de datos: {e}")
        return False

def main():
    """Función principal"""
    print("=" * 60)
    print("Verificación de Configuración del Entorno - NetMind")
    print("=" * 60)
    print()
    
    # Verificar archivo .env
    has_env = check_env_file()
    print()
    
    if not has_env:
        print("\n⚠️  Crea el archivo .env antes de continuar")
        print("   Puedes usar el archivo .env.example como referencia")
        sys.exit(1)
    
    # Verificar variables requeridas
    print("Verificando variables de entorno...")
    try:
        errors, warnings = check_required_vars()
    except Exception as e:
        print(f"✗ Error al verificar variables: {e}")
        print("\n💡 Tip: Asegúrate de que el archivo .env esté en backend/")
        sys.exit(1)
    print()
    
    # Verificar conexión a base de datos
    print("Verificando conexión a base de datos...")
    db_ok = check_database_connection()
    print()
    
    # Resumen
    print("=" * 60)
    if errors:
        print("❌ ERRORES ENCONTRADOS:")
        for error in errors:
            print(f"  - {error}")
        print()
    
    if warnings:
        print("⚠️  ADVERTENCIAS:")
        for warning in warnings:
            print(f"  - {warning}")
        print()
    
    if not errors and db_ok:
        print("✅ Configuración correcta. La aplicación debería funcionar correctamente.")
        sys.exit(0)
    elif not errors:
        print("⚠️  Configuración básica correcta, pero la base de datos no está disponible.")
        print("   En desarrollo, la aplicación puede continuar, pero algunas funciones pueden no estar disponibles.")
        sys.exit(0)
    else:
        print("❌ Hay errores en la configuración. Corrígelos antes de continuar.")
        sys.exit(1)

if __name__ == "__main__":
    main()

