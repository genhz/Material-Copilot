import { computed, ref } from 'vue'
import {
  cancelGenerationCampaign,
  getCampaignCandidates,
  getGenerationCampaign,
} from '../api/material'
import {
  generationRealtimeUrl,
  useRealtimeSocket,
  type RealtimeMessage,
} from './useRealtimeSocket'
import type {
  CampaignCandidateCollection,
  CampaignJob,
} from '../types/material'

const STORAGE_KEY = 'material_generation_campaign_id'

const campaignId = ref<string | null>(null)
const campaign = ref<CampaignJob | null>(null)
const collection = ref<CampaignCandidateCollection | null>(null)
const panelOpen = ref(false)
const isCancelling = ref(false)
const error = ref<string | null>(null)

let requestToken = 0

const { isConnected, connect, close, subscribe, unsubscribe } =
  useRealtimeSocket(handleRealtimeMessage, handleRealtimeReconnect)

const candidates = computed(() => collection.value?.candidates ?? [])
const isActive = computed(
  () =>
    campaign.value?.status === 'queued' ||
    campaign.value?.status === 'running'
)

async function loadCandidates(currentCampaignId: string, token: number) {
  try {
    const next = await getCampaignCandidates(currentCampaignId)
    if (token !== requestToken) return
    collection.value = next
  } catch (requestError: any) {
    if (token !== requestToken) return
    error.value =
      requestError.response?.data?.detail?.message ||
      requestError.message ||
      '无法读取 Campaign 候选'
  }
}

async function refreshSnapshot(currentCampaignId: string, token: number) {
  try {
    const next = await getGenerationCampaign(currentCampaignId)
    if (token !== requestToken) return
    campaign.value = next
    error.value = null
    if (next.status !== 'queued' && next.status !== 'running') {
      await loadCandidates(currentCampaignId, token)
      unsubscribe('generation.campaign', currentCampaignId)
    }
  } catch (requestError: any) {
    if (token !== requestToken) return
    error.value =
      requestError.response?.data?.detail?.message ||
      requestError.message ||
      '无法查询 Campaign'
  }
}

function handleRealtimeMessage(message: RealtimeMessage) {
  if (
    message.channel !== 'generation.campaign' ||
    message.resource_id !== campaignId.value
  ) {
    return
  }

  const payload = message as RealtimeMessage & { campaign?: CampaignJob }
  if (!payload.campaign) return

  campaign.value = payload.campaign
  error.value = null
  if (
    payload.campaign.status !== 'queued' &&
    payload.campaign.status !== 'running'
  ) {
    void loadCandidates(payload.campaign.campaign_id, requestToken)
    unsubscribe('generation.campaign', payload.campaign.campaign_id)
  }
}

function handleRealtimeReconnect() {
  if (campaignId.value) {
    void refreshSnapshot(campaignId.value, requestToken)
  }
}

function openCampaign(nextCampaignId: string) {
  const changed = campaignId.value !== nextCampaignId
  campaignId.value = nextCampaignId
  panelOpen.value = true
  localStorage.setItem(STORAGE_KEY, nextCampaignId)
  if (!changed) return

  requestToken += 1
  campaign.value = null
  collection.value = null
  error.value = null
  subscribe('generation.campaign', nextCampaignId)
  connect(generationRealtimeUrl())
  void refreshSnapshot(nextCampaignId, requestToken)
}

function restoreCampaign() {
  const stored = localStorage.getItem(STORAGE_KEY)
  if (!stored) return
  campaignId.value = stored
  panelOpen.value = false
  subscribe('generation.campaign', stored)
  connect(generationRealtimeUrl())
  void refreshSnapshot(stored, requestToken)
}

function closePanel() {
  panelOpen.value = false
}

function reopenPanel() {
  if (campaignId.value) {
    panelOpen.value = true
  }
}

async function cancel() {
  if (!campaign.value || !isActive.value || isCancelling.value) return
  isCancelling.value = true
  try {
    campaign.value = await cancelGenerationCampaign(
      campaign.value.campaign_id
    )
  } catch (requestError: any) {
    error.value =
      requestError.response?.data?.detail?.message ||
      requestError.message ||
      '取消 Campaign 失败'
  } finally {
    isCancelling.value = false
  }
}

function clearCampaign() {
  if (campaignId.value) {
    unsubscribe('generation.campaign', campaignId.value)
  }
  close()
  localStorage.removeItem(STORAGE_KEY)
  campaignId.value = null
  campaign.value = null
  collection.value = null
  panelOpen.value = false
  error.value = null
}

export function useCampaign() {
  return {
    campaignId,
    campaign,
    candidates,
    collection,
    panelOpen,
    error,
    isCancelling,
    isConnected,
    isActive,
    openCampaign,
    restoreCampaign,
    closePanel,
    reopenPanel,
    cancel,
    clearCampaign,
  }
}
