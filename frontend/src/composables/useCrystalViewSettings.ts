import { reactive } from 'vue'
import {
  DEFAULT_CRYSTAL_SETTINGS,
  type CrystalViewSettings,
  type SupercellSettings,
} from '../components/crystal/crystalViewer'

const settings = reactive<CrystalViewSettings>({
  supercell: { ...DEFAULT_CRYSTAL_SETTINGS.supercell },
  showUnitCell: DEFAULT_CRYSTAL_SETTINGS.showUnitCell,
})

const STORAGE_KEY = 'material_crystal_view_settings'

function loadSettings() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (!stored) return
    const parsed = JSON.parse(stored) as CrystalViewSettings
    settings.supercell = normalizeSupercell(parsed.supercell)
    settings.showUnitCell = parsed.showUnitCell ?? true
  } catch {
    resetSupercell()
  }
}

function persistSettings() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(settings))
}

function normalizeSupercell(value?: Partial<SupercellSettings>): SupercellSettings {
  const clamp = (number: unknown) =>
    Math.max(1, Math.min(Number(number) || 1, 4))
  return {
    a: clamp(value?.a),
    b: clamp(value?.b),
    c: clamp(value?.c),
  }
}

function setSupercell(value: Partial<SupercellSettings>) {
  settings.supercell = normalizeSupercell({
    ...settings.supercell,
    ...value,
  })
  persistSettings()
}

function setPreset(size: number) {
  setSupercell({ a: size, b: size, c: size })
}

function resetSupercell() {
  settings.supercell = { ...DEFAULT_CRYSTAL_SETTINGS.supercell }
  persistSettings()
}

function setShowUnitCell(value: boolean) {
  settings.showUnitCell = value
  persistSettings()
}

loadSettings()

export function useCrystalViewSettings() {
  return {
    settings,
    setSupercell,
    setPreset,
    resetSupercell,
    setShowUnitCell,
  }
}
