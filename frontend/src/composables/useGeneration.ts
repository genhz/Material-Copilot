import { computed, ref } from 'vue'
import type { WorkflowResult } from '../types/agent'
import type {
  CandidateCollection,
  GeneratedCandidate,
} from '../types/material'


const workflowResult = ref<WorkflowResult | null>(null)
const collection = ref<CandidateCollection | null>(null)
const selectedCandidateId = ref<string | null>(null)
const panelOpen = ref(false)

const candidates = computed(() => collection.value?.candidates ?? [])
const selectedCandidate = computed(
  () =>
    candidates.value.find(
      (candidate) => candidate.candidate_id === selectedCandidateId.value
    ) ?? null
)
const hasCandidates = computed(() => candidates.value.length > 0)

function openWorkflowResult(result: WorkflowResult) {
  workflowResult.value = result
  collection.value = {
    candidates: result.candidates,
    invalid_count: 0,
    total_count: result.candidate_count,
    validation: {},
  }
  selectedCandidateId.value = null
  panelOpen.value = true
}

function closePanel() {
  panelOpen.value = false
}

function reopenPanel() {
  if (hasCandidates.value) {
    panelOpen.value = true
  }
}

function selectCandidate(candidate: GeneratedCandidate) {
  selectedCandidateId.value = candidate.candidate_id
}

function clearGeneration() {
  workflowResult.value = null
  collection.value = null
  selectedCandidateId.value = null
  panelOpen.value = false
}

export function useGeneration() {
  return {
    workflowResult,
    candidates,
    collection,
    selectedCandidateId,
    selectedCandidate,
    panelOpen,
    hasCandidates,
    openWorkflowResult,
    closePanel,
    reopenPanel,
    selectCandidate,
    clearGeneration,
  }
}
