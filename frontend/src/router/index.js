import { createRouter, createWebHistory } from 'vue-router'
import { useAuth } from '@/stores/auth.js'

const routes = [
  {
    path: '/',
    name: 'home',
    component: () => import('@/pages/HomePage.vue'),
    meta: { title: 'ResumeAst — AI 求职助手' },
  },
  {
    path: '/login',
    name: 'login',
    component: () => import('@/pages/LoginPage.vue'),
    meta: { title: '登录 — ResumeAst' },
  },
  {
    path: '/register',
    name: 'register',
    component: () => import('@/pages/RegisterPage.vue'),
    meta: { title: '注册 — ResumeAst' },
  },
  {
    path: '/interview',
    name: 'interview-list',
    component: () => import('@/pages/InterviewListPage.vue'),
    meta: { title: '模拟面试 — ResumeAst', requiresAuth: true },
  },
  {
    path: '/interview/config',
    name: 'interview-config',
    component: () => import('@/pages/InterviewConfigPage.vue'),
    meta: { title: '面试配置 — ResumeAst', requiresAuth: true },
  },
  {
    path: '/interview/:id/summary',
    name: 'interview-summary',
    component: () => import('@/pages/InterviewSummaryPage.vue'),
    meta: { title: '面试总结 — ResumeAst', requiresAuth: true },
  },
  {
    path: '/interview/:id',
    name: 'interview-session',
    component: () => import('@/pages/InterviewSessionPage.vue'),
    meta: { title: '模拟面试 — ResumeAst', requiresAuth: true },
  },
  {
    path: '/analysis/github',
    component: () => import('@/layouts/GitHubLayout.vue'),
    meta: { title: 'GitHub 源码分析 — ResumeAst', requiresAuth: true },
    children: [
      { path: '', name: 'github-list', component: () => import('@/pages/github/GitHubListPage.vue') },
      { path: ':id', name: 'github-overview', component: () => import('@/pages/github/GitHubOverviewPage.vue'), meta: { title: '仓库概览 — ResumeAst' } },
      { path: ':id/deep', name: 'github-deep', component: () => import('@/pages/github/GitHubDeepPage.vue'), meta: { title: '深度分析 — ResumeAst' } },
    ],
  },
  {
    path: '/analysis/jd',
    name: 'jd',
    component: () => import('@/pages/JdPage.vue'),
    meta: { title: 'JD 智能分析 — ResumeAst', requiresAuth: true },
  },
  {
    path: '/analysis/resume',
    name: 'resume',
    component: () => import('@/pages/ResumePage.vue'),
    meta: { title: '简历匹配分析 — ResumeAst', requiresAuth: true },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior() {
    return { top: 0 }
  },
})

router.beforeEach((to) => {
  document.title = to.meta.title || 'ResumeAst'

  // Auth guard
  if (to.meta.requiresAuth) {
    const { isLoggedIn } = useAuth()
    if (!isLoggedIn()) {
      return { name: 'login', query: { redirect: to.fullPath } }
    }
  }
})

export default router
