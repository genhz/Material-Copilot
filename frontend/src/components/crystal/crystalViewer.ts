export interface SupercellSettings {
  a: number
  b: number
  c: number
}

export interface CrystalViewSettings {
  supercell: SupercellSettings
  showUnitCell: boolean
}

export const DEFAULT_CRYSTAL_SETTINGS: CrystalViewSettings = {
  supercell: {
    a: 1,
    b: 1,
    c: 1,
  },
  showUnitCell: true,
}

export function supercellRange(settings: SupercellSettings) {
  const range = (size: number) => ({
    min: -Math.floor((size - 1) / 2),
    max: Math.floor(size / 2),
  })
  return {
    x: range(settings.a),
    y: range(settings.b),
    z: range(settings.c),
  }
}
