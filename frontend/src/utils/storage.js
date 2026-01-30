/**
 * Utilidades para manejo de localStorage y sessionStorage
 */

/**
 * Obtiene un valor del localStorage
 * @param {string} key - Clave del valor
 * @param {any} defaultValue - Valor por defecto si no existe
 * @returns {any} - Valor almacenado o valor por defecto
 */
export function getStorageItem(key, defaultValue = null) {
  try {
    const item = localStorage.getItem(key)
    return item ? JSON.parse(item) : defaultValue
  } catch (error) {
    return defaultValue
  }
}

/**
 * Guarda un valor en localStorage
 * @param {string} key - Clave del valor
 * @param {any} value - Valor a guardar
 */
export function setStorageItem(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch (error) {
  }
}

/**
 * Elimina un valor del localStorage
 * @param {string} key - Clave del valor a eliminar
 */
export function removeStorageItem(key) {
  try {
    localStorage.removeItem(key)
  } catch (error) {
  }
}

/**
 * Genera un ID de sesión único
 * @returns {string} - ID de sesión
 */
export function generateSessionId() {
  return `session-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
}

/**
 * Obtiene o crea un ID de sesión
 * @param {string} storageKey - Clave de almacenamiento
 * @returns {string} - ID de sesión
 */
export function getOrCreateSessionId(storageKey) {
  let sessionId = getStorageItem(storageKey)
  if (!sessionId) {
    sessionId = generateSessionId()
    setStorageItem(storageKey, sessionId)
  }
  return sessionId
}

