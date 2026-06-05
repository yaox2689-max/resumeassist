<script setup>
import { computed, ref } from 'vue'
import { INTERVIEW_TYPES, INTERVIEW_STATUS, STATUS_COLORS } from '@/data/interview.js'

const props = defineProps({
  interview: { type: Object, required: true }
})

const emit = defineEmits(['view-summary', 'continue', 'delete'])
const showDeleteConfirm = ref(false)

function handleDelete(e) {
  e.stopPropagation()
  showDeleteConfirm.value = true
}

function confirmDelete(e) {
  e.stopPropagation()
  showDeleteConfirm.value = false
  emit('delete', props.interview.id)
}

function cancelDelete(e) {
  e.stopPropagation()
  showDeleteConfirm.value = false
}

const formattedDate = computed(() => {
  const date = new Date(props.interview.date)
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${month}-${day}`
})

const formattedDuration = computed(() => {
  const duration = props.interview.duration
  if (duration < 60) return `${duration}分钟`
  const hours = Math.floor(duration / 60)
  const minutes = duration % 60
  return `${hours}小时${minutes}分钟`
})

function handleClick() {
  if (props.interview.status === 'completed') {
    emit('view-summary', props.interview.id)
  } else {
    emit('continue', props.interview.id)
  }
}
</script>

<template>
  <div
    class="bg-white dark:bg-surface border border-border-light dark:border-border rounded-xl p-5 transition-all hover:shadow-md hover:border-primary/40 cursor-pointer"
    @click="handleClick"
  >
    <div class="flex items-start gap-4">
      <!-- Icon -->
      <div class="w-10 h-10 rounded-lg bg-gradient-to-br from-[#fce4dc] to-[#f5d8cc] flex items-center justify-center shrink-0">
        <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
          <rect x="4" y="3" width="14" height="16" rx="2" stroke="#E8937A" stroke-width="1.8"/>
          <circle cx="11" cy="9" r="3" stroke="#E8937A" stroke-width="1.3"/>
          <path d="M6 17c0-3 2.2-5 5-5s5 2 5 5" stroke="#E8937A" stroke-width="1.3" stroke-linecap="round"/>
        </svg>
      </div>

      <!-- Content -->
      <div class="flex-1 min-w-0">
        <div class="flex items-center justify-between gap-3">
          <h3 class="text-sm font-semibold text-ink">
            {{ INTERVIEW_TYPES[interview.type] }}
          </h3>
          <div class="flex items-center gap-2">
            <span
              class="px-2 py-1 rounded-full text-xs font-medium"
              :class="STATUS_COLORS[interview.status]"
            >
              {{ INTERVIEW_STATUS[interview.status] }}
            </span>
            <button
              class="delete-btn"
              title="删除面试"
              @click.stop="handleDelete"
            >
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M2 4h10M5 4V2.5a.5.5 0 01.5-.5h3a.5.5 0 01.5.5V4M11 4v7.5a1 1 0 01-1 1H4a1 1 0 01-1-1V4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>
                <line x1="5.5" y1="6.5" x2="5.5" y2="10.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
                <line x1="8.5" y1="6.5" x2="8.5" y2="10.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
              </svg>
            </button>
          </div>
        </div>

        <div class="mt-3 space-y-1.5">
          <div class="flex items-center gap-2 text-xs text-ink-muted">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <rect x="2" y="1" width="10" height="12" rx="1.5" stroke="currentColor" stroke-width="1.2"/>
              <circle cx="7" cy="5" r="2" stroke="currentColor" stroke-width="1"/>
              <path d="M4 11c0-2 1.3-3 3-3s3 1 3 3" stroke="currentColor" stroke-width="1" stroke-linecap="round"/>
            </svg>
            <span>{{ interview.resume }}</span>
          </div>

          <div v-if="interview.projects && interview.projects.length > 0" class="flex items-center gap-2 text-xs text-ink-muted">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <rect x="2" y="2" width="10" height="10" rx="2" stroke="currentColor" stroke-width="1.2"/>
              <path d="M5 7l2 2 2-2" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            <span>{{ interview.projects.join(', ') }}</span>
          </div>

          <div class="flex items-center gap-4 text-xs text-ink-muted">
            <div class="flex items-center gap-1">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <circle cx="7" cy="7" r="5.5" stroke="currentColor" stroke-width="1.2"/>
                <path d="M7 4v3l2 1.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
              </svg>
              <span>{{ formattedDuration }}</span>
            </div>
            <div class="flex items-center gap-1">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <rect x="1.5" y="2.5" width="11" height="9" rx="1.5" stroke="currentColor" stroke-width="1.2"/>
                <line x1="1.5" y1="5.5" x2="12.5" y2="5.5" stroke="currentColor" stroke-width="1.2"/>
                <line x1="4.5" y1="1.5" x2="4.5" y2="3.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
                <line x1="9.5" y1="1.5" x2="9.5" y2="3.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
              </svg>
              <span>{{ formattedDate }}</span>
            </div>
          </div>
        </div>

        <!-- Action Button -->
        <div class="mt-4">
          <button
            v-if="interview.status === 'completed'"
            class="w-full px-4 py-2 text-sm rounded-lg border border-border-light dark:border-border hover:bg-surface hover:border-primary/40 transition-all text-ink"
          >
            查看总结
          </button>
          <button
            v-else
            class="w-full px-4 py-2 text-sm rounded-lg bg-primary text-white hover:bg-primary/90 transition-all"
          >
            继续面试
          </button>
        </div>
      </div>
    </div>

    <!-- Delete Confirmation -->
    <Teleport to="body">
      <div v-if="showDeleteConfirm" class="delete-overlay" @click.self="cancelDelete">
        <div class="delete-dialog">
          <h3 class="delete-dialog__title">确认删除</h3>
          <p class="delete-dialog__desc">删除后将无法恢复该面试记录，确定要删除吗？</p>
          <div class="delete-dialog__actions">
            <button class="delete-dialog__btn delete-dialog__btn--cancel" @click="cancelDelete">取消</button>
            <button class="delete-dialog__btn delete-dialog__btn--confirm" @click="confirmDelete">确认删除</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.delete-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  color: var(--color-ink-muted);
  opacity: 0;
  transition: all 0.2s ease;
  flex-shrink: 0;
}

.bg-white:hover .delete-btn,
:global(.dark) .bg-surface:hover .delete-btn {
  opacity: 1;
}

.delete-btn:hover {
  background: #FEE2E2;
  color: #EF4444;
}

.delete-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(4px);
}

.delete-dialog {
  background: var(--color-white);
  border-radius: var(--radius-2xl);
  padding: var(--space-8);
  max-width: 400px;
  width: 90%;
  box-shadow: var(--shadow-xl);
  animation: dialogIn 0.25s var(--ease-out) both;
}

@keyframes dialogIn {
  from { opacity: 0; transform: scale(0.95) translateY(10px); }
  to { opacity: 1; transform: scale(1) translateY(0); }
}

.delete-dialog__title {
  font-size: var(--text-lg);
  font-weight: 700;
  color: var(--color-ink);
  margin-bottom: var(--space-3);
}

.delete-dialog__desc {
  font-size: var(--text-sm);
  color: var(--color-ink-muted);
  margin-bottom: var(--space-6);
  line-height: var(--leading-relaxed);
}

.delete-dialog__actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-3);
}

.delete-dialog__btn {
  padding: var(--space-2) var(--space-5);
  font-size: var(--text-sm);
  font-weight: 500;
  border-radius: var(--radius-lg);
  transition: all var(--duration-fast) var(--ease-out);
}

.delete-dialog__btn--cancel {
  color: var(--color-ink-muted);
  border: 1px solid var(--color-border-light);
}

.delete-dialog__btn--cancel:hover {
  background: var(--color-surface);
}

.delete-dialog__btn--confirm {
  background: #EF4444;
  color: white;
}

.delete-dialog__btn--confirm:hover {
  background: #DC2626;
}

:global(.dark) .delete-dialog {
  background: var(--color-surface);
}
</style>