import { Grid, Line, OrbitControls, RoundedBox, useGLTF } from '@react-three/drei'
import { Canvas, useFrame, useThree, type ThreeEvent } from '@react-three/fiber'
import {
  AlertTriangle, Cross, DoorOpen, Eye, FireExtinguisher, MessageSquare, Package, ShowerHead,
} from 'lucide-react'
import React, { Component, Suspense, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import * as THREE from 'three'
import { useT } from '@/lib/i18n'
import { cn } from '@/lib/utils'
import { useLab } from '@/store'
import type { Equipment, LabDetail, Status } from '@/types'

const ACCENT = '#3CD0C0'
const PIN_KINDS = new Set(['instrument', 'hood', 'freezer'])
const DEFAULT_CAM = new THREE.Vector3(-6, 20, 23)

function baseY(e: Equipment, all: Equipment[]) {
  if (e.kind === 'bench') return 0
  const bench = all.find(
    (b) => b.kind === 'bench' && Math.abs(b.x - e.x) < b.w / 2 && Math.abs(b.z - e.z) < b.d / 2,
  )
  return bench ? bench.h : 0
}

function useWorld(lab: LabDetail) {
  return useMemo(() => {
    const ox = lab.width / 2
    const oz = lab.depth / 2
    return (x: number, z: number, y = 0) => new THREE.Vector3(x - ox, y, z - oz)
  }, [lab.width, lab.depth])
}

const KIND_COLOR: Record<string, string> = {
  instrument: '#cfd8dc',
  hood: '#8d999f',
  freezer: '#e9eff1',
  storage: '#56636a',
  bench: '#2b363c',
}

export function StatusDot({ status, className }: { status: Status; className?: string }) {
  return (
    <span
      className={cn(
        'inline-block size-3 shrink-0 rounded-full',
        status === 'ok' && 'bg-white',
        status === 'maint' && 'border-[1.5px] border-dashed border-dim bg-[#7C888E]',
        status === 'alert' && 'animate-ring bg-accent',
        status === 'off' && 'bg-muted',
        className,
      )}
    />
  )
}

const anchors = new Map<string, { el: HTMLElement; pos: THREE.Vector3 }>()

function Anchor({ id, position, children }: { id: string; position: THREE.Vector3; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null)
  const { x, y, z } = position
  useLayoutEffect(() => {
    anchors.set(id, { el: ref.current!, pos: new THREE.Vector3(x, y, z) })
    return () => {
      anchors.delete(id)
    }
  }, [id, x, y, z])
  return (
    <div ref={ref} className="absolute left-0 top-0" style={{ visibility: 'hidden' }}>
      <div className="pointer-events-auto -translate-x-1/2 -translate-y-1/2">{children}</div>
    </div>
  )
}

function Projector() {
  const v = useMemo(() => new THREE.Vector3(), [])
  useFrame(({ camera, size }) => {
    anchors.forEach(({ el, pos }) => {
      v.copy(pos).project(camera)
      el.style.transform = `translate(${((v.x + 1) / 2) * size.width}px, ${((1 - v.y) / 2) * size.height}px)`
      el.style.visibility = v.z < 1 ? 'visible' : 'hidden'
    })
  })
  return null
}

function Pin({
  id, position, label, children, onClick, active, showLabel,
}: {
  id: string; position: THREE.Vector3; label?: string; children: ReactNode; onClick?: () => void; active?: boolean
  showLabel: boolean
}) {
  const [hover, setHover] = useState(false)
  return (
    <Anchor id={id} position={position}>
      <button
        onClick={onClick}
        onPointerEnter={() => setHover(true)}
        onPointerLeave={() => setHover(false)}
        className="group flex cursor-pointer flex-col items-center gap-1 select-none"
      >
        <span
          className={cn(
            'flex size-[26px] items-center justify-center rounded-full border border-white/20 bg-surface/90 shadow-lg shadow-black/50 backdrop-blur transition-transform group-hover:scale-110',
            active && 'border-accent ring-2 ring-accent/40',
          )}
        >
          {children}
        </span>
        {label && (showLabel || hover || active) && (
          <span className="whitespace-nowrap rounded-md border border-white/10 bg-surface/85 px-1.5 py-0.5 text-[10.5px] font-medium text-fg backdrop-blur">
            {label}
          </span>
        )}
      </button>
    </Anchor>
  )
}

function Room({ lab }: { lab: LabDetail }) {
  const W = lab.width
  const D = lab.depth
  const wall = '#1b2428'
  return (
    <group>
      <mesh rotation-x={-Math.PI / 2} receiveShadow position={[0, -0.01, 0]}>
        <planeGeometry args={[W, D]} />
        <meshStandardMaterial color="#11181c" roughness={0.95} />
      </mesh>
      <Grid
        args={[W, D]}
        position={[0, 0.002, 0]}
        cellSize={0.5}
        cellThickness={0.5}
        cellColor="#1e272c"
        sectionSize={2}
        sectionThickness={0.8}
        sectionColor="#2a363c"
        fadeDistance={60}
      />
      <mesh position={[0, 1.4, -D / 2 - 0.1]} castShadow receiveShadow>
        <boxGeometry args={[W + 0.4, 2.8, 0.2]} />
        <meshStandardMaterial color={wall} />
      </mesh>
      <mesh position={[-W / 2 - 0.1, 1.4, 0]} castShadow receiveShadow>
        <boxGeometry args={[0.2, 2.8, D]} />
        <meshStandardMaterial color={wall} />
      </mesh>
      <mesh position={[W / 2 + 0.1, 0.15, 0]}>
        <boxGeometry args={[0.2, 0.3, D]} />
        <meshStandardMaterial color={wall} />
      </mesh>
      {(() => {
        const ex = lab.entrance[0] - W / 2
        const gap = 1.6
        const leftW = ex - gap / 2 + W / 2
        const rightW = W / 2 - (ex + gap / 2)
        return (
          <>
            <mesh position={[-W / 2 + leftW / 2, 0.15, D / 2 + 0.1]}>
              <boxGeometry args={[leftW, 0.3, 0.2]} />
              <meshStandardMaterial color={wall} />
            </mesh>
            <mesh position={[W / 2 - rightW / 2, 0.15, D / 2 + 0.1]}>
              <boxGeometry args={[rightW, 0.3, 0.2]} />
              <meshStandardMaterial color={wall} />
            </mesh>
          </>
        )
      })()}
    </group>
  )
}

function GlbModel({ lab }: { lab: LabDetail }) {
  const { scene } = useGLTF(lab.glb_url!)
  const { highlightId, set } = useLab()
  const [hover, setHover] = useState<string | null>(null)
  const meta = lab.model_meta
  const nodeToAsset = useMemo(() => {
    const m = new Map<string, string>()
    Object.entries(meta?.nodes ?? {}).forEach(([node, id]) => m.set(THREE.PropertyBinding.sanitizeNodeName(node), id))
    return m
  }, [meta])
  const model = useMemo(() => {
    const root = scene.clone(true)
    root.traverse((o) => {
      const mesh = o as THREE.Mesh
      if (!mesh.isMesh) return
      mesh.castShadow = true
      mesh.receiveShadow = true
      mesh.material = Array.isArray(mesh.material) ? mesh.material.map((x) => x.clone()) : mesh.material.clone()
      let p: THREE.Object3D | null = mesh
      while (p) {
        const id = nodeToAsset.get(p.name)
        if (id) {
          mesh.userData.assetId = id
          break
        }
        p = p.parent
      }
    })
    return root
  }, [scene, nodeToAsset])
  const statusById = useMemo(() => new Map(lab.equipment.map((e) => [e.id, e.status])), [lab.equipment])
  useEffect(() => {
    model.traverse((o) => {
      const mesh = o as THREE.Mesh
      if (!mesh.isMesh) return
      const id = mesh.userData.assetId as string | undefined
      const lit = !!id && (id === hover || id === highlightId)
      const alert = !!id && statusById.get(id) === 'alert'
      const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material]
      mats.forEach((m) => {
        const std = m as THREE.MeshStandardMaterial
        if (!std.emissive) return
        std.emissive.set(lit || alert ? ACCENT : '#000000')
        std.emissiveIntensity = lit ? 0.35 : alert ? 0.15 : 0
      })
    })
  }, [model, hover, highlightId, statusById])
  const offset = meta?.offset ?? [0, 0, 0]
  const assetOf = (o: THREE.Object3D) => o.userData.assetId as string | undefined
  return (
    <primitive
      object={model}
      position={[-offset[0] - lab.width / 2, -offset[1], -offset[2] - lab.depth / 2]}
      onClick={(ev: ThreeEvent<MouseEvent>) => {
        const id = assetOf(ev.object)
        if (!id || ev.delta > 5) return
        ev.stopPropagation()
        set({ equipmentId: id, highlightId: id })
      }}
      onPointerOver={(ev: ThreeEvent<PointerEvent>) => {
        const id = assetOf(ev.object)
        if (!id) return
        ev.stopPropagation()
        setHover(id)
        document.body.style.cursor = 'pointer'
      }}
      onPointerOut={() => {
        setHover(null)
        document.body.style.cursor = ''
      }}
    />
  )
}

class SafeBoundary extends Component<{ children: ReactNode; fallback: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children
  }
}

function EquipmentMesh({ e, all, world }: { e: Equipment; all: Equipment[]; world: ReturnType<typeof useWorld> }) {
  const [hover, setHover] = useState(false)
  const { highlightId, route, set } = useLab()
  const y0 = baseY(e, all)
  const pos = world(e.x, e.z, y0)
  const lit = hover || highlightId === e.id || route?.order.includes(e.id)
  const color = e.status === 'off' ? '#3a4449' : KIND_COLOR[e.kind] ?? '#9aa6ac'
  const emissive = lit ? ACCENT : e.status === 'alert' ? ACCENT : '#000000'
  const emissiveIntensity = lit ? 0.35 : e.status === 'alert' ? 0.12 : 0

  const click = (ev: ThreeEvent<MouseEvent>) => {
    ev.stopPropagation()
    if (ev.delta > 5) return
    set({ equipmentId: e.id, highlightId: e.id })
  }
  const handlers = {
    onClick: click,
    onPointerOver: (ev: ThreeEvent<PointerEvent>) => {
      ev.stopPropagation()
      setHover(true)
      document.body.style.cursor = 'pointer'
    },
    onPointerOut: () => {
      setHover(false)
      document.body.style.cursor = ''
    },
  }

  if (e.kind === 'bench') {
    return (
      <group position={pos} {...handlers}>
        <mesh position={[0, e.h - 0.04, 0]} castShadow receiveShadow>
          <boxGeometry args={[e.w, 0.08, e.d]} />
          <meshStandardMaterial color="#3a474d" emissive={emissive} emissiveIntensity={emissiveIntensity} />
        </mesh>
        <mesh position={[0, (e.h - 0.08) / 2, 0]} castShadow>
          <boxGeometry args={[e.w - 0.15, e.h - 0.08, e.d - 0.2]} />
          <meshStandardMaterial color={color} roughness={0.9} />
        </mesh>
      </group>
    )
  }
  return (
    <group position={pos} {...handlers}>
      <RoundedBox args={[e.w, e.h, e.d]} radius={Math.min(0.06, e.h / 4)} position={[0, e.h / 2, 0]} castShadow>
        <meshStandardMaterial
          color={color}
          roughness={0.55}
          metalness={0.1}
          emissive={emissive}
          emissiveIntensity={emissiveIntensity}
        />
      </RoundedBox>
      {e.kind === 'hood' && (
        <mesh position={[0, e.h * 0.55, e.d / 2 + 0.01]}>
          <planeGeometry args={[e.w * 0.85, e.h * 0.4]} />
          <meshStandardMaterial color="#9fe9e1" transparent opacity={0.25} />
        </mesh>
      )}
      {(e.kind === 'instrument' || e.kind === 'freezer') && (
        <mesh position={[e.w * 0.18, e.h * 0.68, e.d / 2 + 0.005]}>
          <planeGeometry args={[e.w * 0.35, Math.min(0.22, e.h * 0.25)]} />
          <meshBasicMaterial color={e.status === 'alert' ? ACCENT : '#0b0f12'} />
        </mesh>
      )}
      {e.kind === 'storage' && (
        <mesh position={[0, e.h / 2, e.d / 2 + 0.005]}>
          <planeGeometry args={[0.02, e.h * 0.9]} />
          <meshBasicMaterial color="#0b0f12" />
        </mesh>
      )}
    </group>
  )
}

const POINT_ICON: Record<string, typeof DoorOpen> = {
  exit: DoorOpen, eyewash: Eye, shower: ShowerHead, firstaid: Cross, extinguisher: FireExtinguisher,
}

function LayerPins({ lab, world }: { lab: LabDetail; world: ReturnType<typeof useWorld> }) {
  const { layer, showLabels, set, highlightId, quests, channels, unread } = useLab()
  const t = useT()
  const top = (e: Equipment) => world(e.x, e.z, baseY(e, lab.equipment) + e.h + 0.45)
  const open = (id: string) => set({ equipmentId: id, highlightId: id })

  if (layer === 'infra') {
    return (
      <>
        {lab.equipment.filter((e) => PIN_KINDS.has(e.kind)).map((e) => (
          <Pin key={e.id} id={`eq-${e.id}`} position={top(e)} label={e.name} showLabel={showLabels} active={highlightId === e.id}
            onClick={() => open(e.id)}>
            <StatusDot status={e.status} />
          </Pin>
        ))}
      </>
    )
  }

  if (layer === 'inventory') {
    const byLoc = new Map<string, { n: number; alerts: number }>()
    lab.materials.forEach((m) => {
      const v = byLoc.get(m.location_id) ?? { n: 0, alerts: 0 }
      v.n += 1
      v.alerts += m.forecast.alerts.length ? 1 : 0
      byLoc.set(m.location_id, v)
    })
    return (
      <>
        {lab.equipment.filter((e) => byLoc.has(e.id)).map((e) => {
          const v = byLoc.get(e.id)!
          return (
            <Pin key={e.id} id={`eq-${e.id}`} position={top(e)} showLabel={showLabels} active={highlightId === e.id}
              label={`${e.name} · ${t('pin.items', { n: v.n })}${v.alerts ? ` · ${t('pin.alerts', { n: v.alerts })}` : ''}`} onClick={() => open(e.id)}>
              {v.alerts ? <span className="size-3 animate-ring rounded-full bg-accent" /> : <Package className="size-3.5 text-fg" />}
            </Pin>
          )
        })}
      </>
    )
  }

  if (layer === 'safety') {
    return (
      <>
        {lab.points.map((p) => {
          const Icon = POINT_ICON[p.kind] ?? AlertTriangle
          return (
            <Pin key={p.id} id={p.id} position={world(p.x, p.z, 0.9)} label={p.label} showLabel={showLabels}>
              <Icon className="size-3.5 text-fg" />
            </Pin>
          )
        })}
        {lab.zones.map((z) => (
          <Pin key={z.id} id={z.id} position={world(z.x, z.z, 2.6)} label={z.label} showLabel={showLabels}>
            <AlertTriangle className="size-3.5 text-accent" />
          </Pin>
        ))}
        {lab.equipment.filter((e) => e.status !== 'ok').map((e) => (
          <Pin key={e.id} id={`eq-${e.id}`} position={top(e)} label={e.name} showLabel={showLabels} onClick={() => open(e.id)}>
            <StatusDot status={e.status} />
          </Pin>
        ))}
      </>
    )
  }

  if (layer === 'social') {
    return (
      <>
        {lab.equipment
          .filter((e) => (e.open_incidents ?? 0) > 0 || channels.some((c) => c.equipment_id === e.id))
          .map((e) => {
            const ch = channels.find((c) => c.equipment_id === e.id)
            const n = (ch && unread[ch.id]) || 0
            return (
              <Pin key={e.id} id={`eq-${e.id}`} position={top(e)} showLabel={showLabels} onClick={() => open(e.id)}
                label={`${e.name}${ch ? ` · ${t('pin.discussion')}` : ''}${e.open_incidents ? ` · ${t('pin.openIssues', { n: e.open_incidents })}` : ''}`}>
                <MessageSquare className={cn('size-3.5', n ? 'text-accent' : 'text-fg')} />
              </Pin>
            )
          })}
      </>
    )
  }

  const qs = [...(quests?.mine ?? []), ...(quests?.pool ?? [])].filter((q) => q.target_id)
  const byTarget = new Map<string, number>()
  qs.forEach((q) => byTarget.set(q.target_id!, (byTarget.get(q.target_id!) ?? 0) + 1))
  return (
    <>
      {lab.equipment.filter((e) => byTarget.has(e.id)).map((e) => (
        <Pin key={e.id} id={`eq-${e.id}`} position={top(e)} showLabel={showLabels} active={highlightId === e.id}
          label={`${e.name} · ${t('pin.quests', { n: byTarget.get(e.id)! })}`}
          onClick={() => open(e.id)}>
          <span className="font-mono text-[11px] font-bold text-accent">{byTarget.get(e.id)}</span>
        </Pin>
      ))}
    </>
  )
}

function Zones({ lab, world }: { lab: LabDetail; world: ReturnType<typeof useWorld> }) {
  const layer = useLab((s) => s.layer)
  if (layer !== 'safety') return null
  return (
    <>
      {lab.zones.map((z) => {
        const p = world(z.x, z.z, 0.01)
        const hw = z.w / 2
        const hd = z.d / 2
        return (
          <group key={z.id} position={p}>
            <mesh rotation-x={-Math.PI / 2}>
              <planeGeometry args={[z.w, z.d]} />
              <meshBasicMaterial color={ACCENT} transparent opacity={0.08} depthWrite={false} />
            </mesh>
            <Line
              points={[[-hw, 0.01, -hd], [hw, 0.01, -hd], [hw, 0.01, hd], [-hw, 0.01, hd], [-hw, 0.01, -hd]]}
              color={ACCENT}
              lineWidth={1.5}
              dashed
              dashSize={0.3}
              gapSize={0.2}
            />
          </group>
        )
      })}
    </>
  )
}

function RouteLine({ world }: { world: ReturnType<typeof useWorld> }) {
  const route = useLab((s) => s.route)
  const ref = useRef<{ material: { dashOffset: number } } | null>(null)
  useFrame((_, dt) => {
    if (ref.current) ref.current.material.dashOffset -= dt * 1.5
  })
  if (!route || route.points.length < 2) return null
  const pts = route.points.map(([x, z]) => world(x, z, 0.06))
  return (
    <>
      <Line ref={ref as never} points={pts} color={ACCENT} lineWidth={4} dashed dashSize={0.35} gapSize={0.2} />
    </>
  )
}

function RouteMarkers({ lab, world }: { lab: LabDetail; world: ReturnType<typeof useWorld> }) {
  const t = useT()
  const route = useLab((s) => s.route)
  if (!route || route.points.length < 2) return null
  const [sx, sz] = route.points[0]
  const byId = new Map(lab.equipment.map((e) => [e.id, e]))
  return (
    <>
      <Anchor id="route-start" position={world(sx, sz, 0.06)}>
        <span className="rounded-full bg-fg px-2 py-0.5 font-mono text-[10px] font-bold text-canvas">{t('pin.start')}</span>
      </Anchor>
      {route.order.map((id, i) => {
        const e = byId.get(id)
        if (!e) return null
        return (
          <Anchor key={id} id={`route-${id}`} position={world(e.x, e.z, baseY(e, lab.equipment) + e.h + 1.05)}>
            <span className="flex size-6 items-center justify-center rounded-full bg-accent font-mono text-xs font-bold text-accent-ink shadow-lg">
              {i + 1}
            </span>
          </Anchor>
        )
      })}
    </>
  )
}

function CameraRig({ lab }: { lab: LabDetail }) {
  const controls = useRef<React.ComponentRef<typeof OrbitControls>>(null)
  const { camera } = useThree()
  const cmd = useLab((s) => s.cameraCmd)
  const anim = useRef<{ t: number; dur: number; apply: (k: number) => void } | null>(null)
  const world = useWorld(lab)

  useEffect(() => {
    const c = controls.current
    if (!cmd || !c) return
    const target0 = c.target.clone()
    const pos0 = camera.position.clone()
    const offset0 = pos0.clone().sub(target0)
    let apply: (k: number) => void
    if (cmd.type === 'rotate') {
      apply = (k) => {
        const off = offset0.clone().applyAxisAngle(new THREE.Vector3(0, 1, 0), cmd.value * k)
        camera.position.copy(target0.clone().add(off))
      }
    } else if (cmd.type === 'zoom') {
      const len = THREE.MathUtils.clamp(offset0.length() * cmd.value, c.minDistance, c.maxDistance)
      apply = (k) => {
        const l = THREE.MathUtils.lerp(offset0.length(), len, k)
        camera.position.copy(target0.clone().add(offset0.clone().setLength(l)))
      }
    } else {
      let target1 = new THREE.Vector3()
      let pos1 = DEFAULT_CAM.clone().multiplyScalar(Math.max(1, Math.max(lab.width, lab.depth * 1.4) / 20))
      if (cmd.type === 'focus') {
        const e = lab.equipment.find((x) => x.id === cmd.id)
        if (!e) return
        target1 = world(e.x, e.z, baseY(e, lab.equipment) + e.h / 2)
        pos1 = target1.clone().add(offset0.clone().setLength(9))
      }
      apply = (k) => {
        c.target.lerpVectors(target0, target1, k)
        camera.position.lerpVectors(pos0, pos1, k)
      }
    }
    anim.current = { t: 0, dur: 0.6, apply }
  }, [cmd, camera, lab, world])

  const { sideOpen, chatOpen } = useLab()
  const size = useThree((st) => st.size)
  useEffect(() => {
    const cam = camera as THREE.PerspectiveCamera
    const wide = size.width >= 1024
    const shift = wide ? (sideOpen ? 200 : 0) - (chatOpen ? 190 : 0) : 0
    if (shift) cam.setViewOffset(size.width, size.height, shift, 0, size.width, size.height)
    else cam.clearViewOffset()
    cam.updateProjectionMatrix()
  }, [sideOpen, chatOpen, size, camera])

  useFrame((_, dt) => {
    const a = anim.current
    if (!a) return
    a.t = Math.min(a.dur, a.t + dt)
    const k = 1 - Math.pow(1 - a.t / a.dur, 3)
    a.apply(k)
    controls.current?.update()
    if (a.t >= a.dur) anim.current = null
  })

  return (
    <OrbitControls
      ref={controls}
      makeDefault
      enableDamping
      dampingFactor={0.07}
      rotateSpeed={0.75}
      zoomSpeed={0.9}
      panSpeed={0.7}
      minDistance={4}
      maxDistance={Math.max(36, Math.max(lab.width, lab.depth) * 2)}
      minPolarAngle={0.18}
      maxPolarAngle={Math.PI / 2.15}
      touches={{ ONE: THREE.TOUCH.ROTATE, TWO: THREE.TOUCH.DOLLY_PAN }}
    />
  )
}

function Scene({ lab }: { lab: LabDetail }) {
  const world = useWorld(lab)
  const set = useLab((s) => s.set)
  const modelAssets = useMemo(() => new Set(lab.glb_url ? Object.values(lab.model_meta?.nodes ?? {}) : []), [lab.glb_url, lab.model_meta])
  return (
    <>
      <color attach="background" args={['#0B0F12']} />
      <fog attach="fog" args={['#0B0F12', 30 * Math.max(1, lab.width / 20), 60 * Math.max(1, lab.width / 20)]} />
      <ambientLight intensity={0.7} />
      <directionalLight
        position={[8, 14, 10]}
        intensity={1.4}
        castShadow
        shadow-mapSize={[2048, 2048]}
        shadow-camera-left={-14}
        shadow-camera-right={14}
        shadow-camera-top={12}
        shadow-camera-bottom={-12}
      />
      <directionalLight position={[-10, 6, -8]} intensity={0.45} color="#D8EEF0" />
      <group onPointerMissed={() => set({ highlightId: null })}>
        {lab.glb_url ? (
          <SafeBoundary fallback={<Room lab={lab} />}>
            <Suspense fallback={<Room lab={lab} />}>
              <GlbModel lab={lab} />
            </Suspense>
          </SafeBoundary>
        ) : (
          <Room lab={lab} />
        )}
        {lab.equipment.filter((e) => !modelAssets.has(e.id)).map((e) => (
          <EquipmentMesh key={e.id} e={e} all={lab.equipment} world={world} />
        ))}
      </group>
      <Zones lab={lab} world={world} />
      <Projector />
      <RouteLine world={world} />
      <CameraRig lab={lab} />
    </>
  )
}

function Overlay({ lab }: { lab: LabDetail }) {
  const world = useWorld(lab)
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden">
      <LayerPins lab={lab} world={world} />
      <RouteMarkers lab={lab} world={world} />
    </div>
  )
}

export default function LabScene() {
  const lab = useLab((s) => s.lab)
  return (
    <div className="absolute inset-0 touch-none">
      <Canvas shadows dpr={[1, 2]} camera={{ position: DEFAULT_CAM.toArray(), fov: 38, near: 0.1, far: 400 }}>
        {lab && <Scene key={lab.id} lab={lab} />}
      </Canvas>
      {lab && <Overlay key={lab.id} lab={lab} />}
    </div>
  )
}
