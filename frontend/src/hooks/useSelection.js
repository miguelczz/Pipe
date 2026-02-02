import { useState, useCallback, useEffect } from 'react'

/**
 * Hook para manejar selección múltiple de items
 * 
 * @param {Array} items - Array de items a seleccionar
 * @param {string} keyField - Campo único que identifica cada item (default: 'id')
 * @returns {Object} - Estado y funciones de selección
 */
export function useSelection(items = [], keyField = 'id') {
  const [selectedIds, setSelectedIds] = useState(new Set())
  const [selectionMode, setSelectionMode] = useState(false)

  // Limpiar selección cuando cambian los items
  useEffect(() => {
    if (!selectionMode) {
      setSelectedIds(new Set())
    }
  }, [items, selectionMode])

  const toggleSelection = useCallback((id) => {
    setSelectedIds((prev) => {
      const newSet = new Set(prev)
      if (newSet.has(id)) {
        newSet.delete(id)
      } else {
        newSet.add(id)
      }
      return newSet
    })
  }, [])

  const selectAll = useCallback(() => {
    const allIds = items.map((item) => item[keyField]).filter(Boolean)
    setSelectedIds(new Set(allIds))
  }, [items, keyField])

  const deselectAll = useCallback(() => {
    setSelectedIds(new Set())
  }, [])

  const toggleSelectionMode = useCallback(() => {
    setSelectionMode((prev) => {
      if (prev) {
        // Al salir del modo selección, limpiar selección
        setSelectedIds(new Set())
      }
      return !prev
    })
  }, [])

  const isSelected = useCallback(
    (id) => {
      return selectedIds.has(id)
    },
    [selectedIds]
  )

  const getSelectedItems = useCallback(() => {
    return items.filter((item) => selectedIds.has(item[keyField]))
  }, [items, selectedIds, keyField])

  const selectItem = useCallback((id) => {
    setSelectedIds((prev) => new Set([...prev, id]))
  }, [])

  const deselectItem = useCallback((id) => {
    setSelectedIds((prev) => {
      const newSet = new Set(prev)
      newSet.delete(id)
      return newSet
    })
  }, [])

  return {
    selectedIds: Array.from(selectedIds),
    selectedCount: selectedIds.size,
    selectionMode,
    toggleSelection,
    selectAll,
    deselectAll,
    toggleSelectionMode,
    isSelected,
    getSelectedItems,
    selectItem,
    deselectItem,
    setSelectionMode,
  }
}
