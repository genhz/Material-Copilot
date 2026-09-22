import type { Viewer } from 'molstar/lib/apps/viewer/app'
import type { Vec3 } from 'molstar/lib/mol-math/linear-algebra'
import type { CrystalViewSettings } from '../components/crystal/crystalViewer'
import { supercellRange } from '../components/crystal/crystalViewer'

type Vec3Constructor = typeof Vec3

export class MolstarAdapter {
  private viewer: Viewer | null = null
  private vector: Vec3Constructor | null = null

  async mount(container: HTMLElement) {
    const [{ Viewer: ViewerClass }, { Vec3: VectorClass }] = await Promise.all([
      import('molstar/lib/apps/viewer/app'),
      import('molstar/lib/mol-math/linear-algebra'),
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
  }

  async render(
    cif: string,
    settings: CrystalViewSettings,
  ) {
    if (!this.viewer || !this.vector) return

    const plugin = this.viewer.plugin
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
      'auto',
      {
        theme: {
          globalName: 'element-symbol',
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
    this.viewer?.dispose()
    this.viewer = null
    this.vector = null
  }
}
