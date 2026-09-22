import type { Viewer } from 'molstar/lib/apps/viewer/app'
import type { Vec3 } from 'molstar/lib/mol-math/linear-algebra'
import type { CrystalViewSettings } from '../components/crystal/crystalViewer'
import { supercellRange } from '../components/crystal/crystalViewer'

type Vec3Constructor = typeof Vec3

function normalizeElementSymbol(symbol: string) {
  const value = symbol.trim()
  if (value.length <= 1) return value.toUpperCase()
  return `${value[0].toUpperCase()}${value.slice(1).toLowerCase()}`
}

export interface AtomHoverInfo {
  symbol: string
  atomicNumber: number | null
  atomId: string | number | null
  x: number
  y: number
}

export class MolstarAdapter {
  private viewer: Viewer | null = null
  private vector: Vec3Constructor | null = null
  private hoverSubscription: { unsubscribe(): void } | null = null

  onHover: ((info: AtomHoverInfo | null) => void) | null = null

  async mount(container: HTMLElement) {
    const [
      { Viewer: ViewerClass },
      { Vec3: VectorClass },
      { StructureElement, Unit, StructureProperties },
    ] = await Promise.all([
      import('molstar/lib/apps/viewer/app'),
      import('molstar/lib/mol-math/linear-algebra'),
      import('molstar/lib/mol-model/structure'),
    ])

    this.vector = VectorClass
    this.viewer = await ViewerClass.create(container, {
      layoutIsExpanded: false,
      layoutShowControls: false,
      layoutShowRemoteState: false,
      layoutShowSequence: false,
      layoutShowLog: false,
      layoutShowLeftPanel: false,
      viewportShowControls: false,
      viewportShowSettings: false,
      viewportShowExpand: false,
      viewportShowSelectionMode: false,
      viewportShowAnimation: false,
      viewportShowTrajectoryControls: false,
      viewportShowScreenshotControls: false,
      viewportShowReset: false,
      powerPreference: 'high-performance',
    })

    this.hoverSubscription =
      this.viewer.plugin.behaviors.interaction.hover.subscribe((event) => {
        const page = event.page
        const loci = event.current.loci

        if (
          !page ||
          event.buttons !== 0 ||
          !StructureElement.Loci.is(loci) ||
          StructureElement.Loci.isEmpty(loci)
        ) {
          this.emitHover(null)
          return
        }

        const location = StructureElement.Loci.getFirstLocation(loci)
        if (!location || !Unit.isAtomic(location.unit)) {
          this.emitHover(null)
          return
        }

        const symbol = StructureProperties.atom.type_symbol(location)
        const atomicNumber =
          location.unit.model.atomicHierarchy.derived.atom.atomicNumber[
            location.element
          ]
        const label = StructureProperties.atom.label_atom_id(location)
        const id = StructureProperties.atom.id(location)

        this.emitHover({
          symbol: normalizeElementSymbol(symbol),
          atomicNumber:
            Number.isFinite(atomicNumber) && atomicNumber > 0
              ? atomicNumber
              : null,
          atomId: label || (Number.isFinite(id) ? id : null),
          x: page[0],
          y: page[1],
        })
      })
  }

  async render(
    cif: string,
    settings: CrystalViewSettings,
  ) {
    if (!this.viewer || !this.vector) return

    const plugin = this.viewer.plugin
    this.emitHover(null)
    await plugin.clear(false)

    if (!cif.trim()) return

    const data = await plugin.builders.data.rawData({
      data: cif,
      label: 'Crystal structure',
    })
    const trajectory = await plugin.builders.structure.parseTrajectory(
      data,
      'cifCore'
    )
    const builder = plugin.builders.structure
    const model = await builder.createModel(trajectory)
    const modelProperties = await builder.insertModelProperties(model)
    const range = supercellRange(settings.supercell)
    const min = this.vector.create(range.x.min, range.y.min, range.z.min)
    const max = this.vector.create(range.x.max, range.y.max, range.z.max)

    const structure = await builder.createStructure(
      modelProperties || model,
      {
        name: 'symmetry',
        params: {
          ijkMin: min,
          ijkMax: max,
          dynamicBonds:
            settings.supercell.a *
              settings.supercell.b *
              settings.supercell.c >
            1,
        },
      }
    )
    const structureProperties = await builder.insertStructureProperties(
      structure
    )

    if (settings.showUnitCell) {
      await builder.tryCreateUnitcell(
        modelProperties || model,
        undefined,
        { isHidden: false }
      )
    }

    await builder.representation.applyPreset(
      structureProperties,
      'atomic-detail',
      {
        quality:
          settings.supercell.a *
            settings.supercell.b *
            settings.supercell.c >
          1
            ? 'medium'
            : 'high',
        theme: {
          globalName: 'element-symbol',
          carbonColor: 'element-symbol',
        },
      }
    )

    plugin.managers.camera.focusObject({ durationMs: 0 })
  }

  resetView() {
    this.viewer?.plugin.managers.camera.focusObject({ durationMs: 250 })
  }

  resize() {
    this.viewer?.handleResize()
  }

  dispose() {
    this.emitHover(null)
    this.hoverSubscription?.unsubscribe()
    this.hoverSubscription = null
    this.viewer?.dispose()
    this.viewer = null
    this.vector = null
    this.onHover = null
  }

  private emitHover(info: AtomHoverInfo | null) {
    this.onHover?.(info)
  }
}
