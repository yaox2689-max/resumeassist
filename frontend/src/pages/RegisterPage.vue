<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/api/index.js'
import { useAuth } from '@/stores/auth.js'
import CapybaraLogo from '@/components/common/CapybaraLogo.vue'
import ThemeToggle from '@/components/common/ThemeToggle.vue'

const router = useRouter()
const { setAuth } = useAuth()

const username = ref('')
const password = ref('')
const confirmPassword = ref('')
const error = ref('')
const loading = ref(false)

async function handleRegister() {
  error.value = ''
  if (!username.value.trim()) {
    error.value = '请输入用户名'
    return
  }
  if (username.value.trim().length < 2) {
    error.value = '用户名至少2个字符'
    return
  }
  if (!password.value.trim()) {
    error.value = '请输入密码'
    return
  }
  if (password.value.trim().length < 4) {
    error.value = '密码至少4个字符'
    return
  }
  if (password.value !== confirmPassword.value) {
    error.value = '两次密码输入不一致'
    return
  }

  loading.value = true
  try {
    const res = await api.register(username.value.trim(), password.value.trim())
    setAuth(res.token, { user_id: res.user_id, username: res.username })
    router.push('/interview')
  } catch (e) {
    error.value = e.message || '注册失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen flex flex-col bg-base dark:bg-base transition-theme">
    <!-- Top bar -->
    <nav
      class="fixed top-0 left-0 right-0 z-[100] flex items-center"
      style="height: var(--nav-height); background: rgba(255,252,247,0.85); backdropFilter: blur(16px); borderBottom: 1px solid var(--color-border-light)"
    >
      <div class="w-full flex items-center justify-between mx-auto px-6" style="max-width: var(--max-width)">
        <router-link to="/" class="flex items-center gap-3 text-xl font-bold no-underline" style="font-family: var(--font-heading); color: var(--color-ink);">
          <CapybaraLogo :size="36" />
          ResumeAst
        </router-link>
        <ThemeToggle />
      </div>
    </nav>

    <!-- Register form -->
    <div class="flex-1 flex items-center justify-center px-4" style="padding-top: var(--nav-height);">
      <div class="w-full max-w-sm p-8 rounded-2xl" style="background: var(--color-white); border: 1px solid var(--color-border-light);">
        <h1 class="text-2xl font-bold mb-1" style="font-family: var(--font-heading); color: var(--color-ink);">注册</h1>
        <p class="text-sm mb-6" style="color: var(--color-ink-muted);">创建你的 ResumeAst 账号</p>

        <form @submit.prevent="handleRegister" class="flex flex-col gap-4">
          <div>
            <label class="block text-sm font-medium mb-1" style="color: var(--color-ink-light);">用户名</label>
            <input
              v-model="username"
              type="text"
              placeholder="请输入用户名"
              class="w-full px-3 py-2 rounded-lg text-sm outline-none transition-colors"
              style="border: 1px solid var(--color-border); background: var(--color-base); color: var(--color-ink);"
              @focus="$event.target.style.borderColor = 'var(--color-primary)'"
              @blur="$event.target.style.borderColor = 'var(--color-border)'"
            />
          </div>

          <div>
            <label class="block text-sm font-medium mb-1" style="color: var(--color-ink-light);">密码</label>
            <input
              v-model="password"
              type="password"
              placeholder="请输入密码（至少4位）"
              class="w-full px-3 py-2 rounded-lg text-sm outline-none transition-colors"
              style="border: 1px solid var(--color-border); background: var(--color-base); color: var(--color-ink);"
              @focus="$event.target.style.borderColor = 'var(--color-primary)'"
              @blur="$event.target.style.borderColor = 'var(--color-border)'"
            />
          </div>

          <div>
            <label class="block text-sm font-medium mb-1" style="color: var(--color-ink-light);">确认密码</label>
            <input
              v-model="confirmPassword"
              type="password"
              placeholder="再次输入密码"
              class="w-full px-3 py-2 rounded-lg text-sm outline-none transition-colors"
              style="border: 1px solid var(--color-border); background: var(--color-base); color: var(--color-ink);"
              @focus="$event.target.style.borderColor = 'var(--color-primary)'"
              @blur="$event.target.style.borderColor = 'var(--color-border)'"
              @keyup.enter="handleRegister"
            />
          </div>

          <p v-if="error" class="text-sm" style="color: #EF4444;">{{ error }}</p>

          <button
            type="submit"
            :disabled="loading"
            class="w-full py-2.5 rounded-lg text-sm font-medium transition-all"
            style="background: var(--color-ink); color: var(--color-white);"
            :class="loading ? 'opacity-60' : 'hover:opacity-90'"
          >
            {{ loading ? '注册中...' : '注册' }}
          </button>
        </form>

        <p class="text-sm text-center mt-6" style="color: var(--color-ink-muted);">
          已有账号？
          <router-link to="/login" style="color: var(--color-primary); font-weight: 500;">登录</router-link>
        </p>
      </div>
    </div>
  </div>
</template>
