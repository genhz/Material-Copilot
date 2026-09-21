import { ref } from 'vue'

export interface RealtimeMessage {
  type: string
  channel?: string
  resource_id?: string
  job?: unknown
  code?: string
  message?: string
  request_id?: string
}

interface Subscription {
  channel: string
  resource_id: string
}

export function useRealtimeSocket(
  onMessage: (message: RealtimeMessage) => void,
  onReconnect?: () => void
) {
  const isConnected = ref(false)
  const socket = ref<WebSocket | null>(null)
  const subscriptions = new Map<string, Subscription>()

  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let heartbeatTimer: ReturnType<typeof setInterval> | null = null
  let reconnectAttempts = 0
  let manualClose = false
  let socketUrl = ''

  function subscriptionKey(subscription: Subscription) {
    return `${subscription.channel}:${subscription.resource_id}`
  }

  function clearTimers() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    if (heartbeatTimer) {
      clearInterval(heartbeatTimer)
      heartbeatTimer = null
    }
  }

  function send(payload: Record<string, unknown>) {
    if (socket.value?.readyState === WebSocket.OPEN) {
      socket.value.send(JSON.stringify(payload))
      return true
    }
    return false
  }

  function subscribe(channel: string, resourceId: string) {
    const subscription = { channel, resource_id: resourceId }
    subscriptions.set(subscriptionKey(subscription), subscription)
    send({
      action: 'subscribe',
      channel,
      resource_id: resourceId,
      request_id: crypto.randomUUID(),
    })
  }

  function unsubscribe(channel: string, resourceId: string) {
    const subscription = { channel, resource_id: resourceId }
    subscriptions.delete(subscriptionKey(subscription))
    send({
      action: 'unsubscribe',
      channel,
      resource_id: resourceId,
      request_id: crypto.randomUUID(),
    })
  }

  function scheduleReconnect() {
    if (manualClose || reconnectTimer || !socketUrl) return

    reconnectAttempts += 1
    const delay = Math.min(1000 * 2 ** (reconnectAttempts - 1), 15000)
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null
      connect(socketUrl)
    }, delay)
  }

  function connect(url: string) {
    manualClose = false
    socketUrl = url
    clearTimers()

    if (
      socket.value?.readyState === WebSocket.OPEN ||
      socket.value?.readyState === WebSocket.CONNECTING
    ) {
      return
    }

    const nextSocket = new WebSocket(url)
    socket.value = nextSocket

    nextSocket.onopen = () => {
      isConnected.value = true
      reconnectAttempts = 0
      for (const subscription of subscriptions.values()) {
        send({
          action: 'subscribe',
          ...subscription,
          request_id: crypto.randomUUID(),
        })
      }
      heartbeatTimer = setInterval(() => {
        send({ action: 'ping', request_id: crypto.randomUUID() })
      }, 20000)
      onReconnect?.()
    }

    nextSocket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data) as RealtimeMessage
        if (message.type !== 'pong') {
          onMessage(message)
        }
      } catch (error) {
        console.error('[RealtimeSocket] Invalid message', error)
      }
    }

    nextSocket.onerror = () => {
      nextSocket.close()
    }

    nextSocket.onclose = () => {
      isConnected.value = false
      clearTimers()
      if (socket.value === nextSocket) {
        socket.value = null
      }
      scheduleReconnect()
    }
  }

  function close() {
    manualClose = true
    clearTimers()
    subscriptions.clear()
    socket.value?.close()
    socket.value = null
    isConnected.value = false
  }

  return {
    isConnected,
    connect,
    close,
    send,
    subscribe,
    unsubscribe,
  }
}

export function generationRealtimeUrl() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/api/ws`
}
