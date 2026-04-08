<script setup lang="ts">
import { computed, ref } from 'vue';
import { getGateway } from '@/shared/gateway/service';
import { useAuthStore } from '@/entities/auth/store';
import { useAppStore } from '@/entities/app/store';

const gateway = getGateway();
const authStore = useAuthStore();
const appStore = useAppStore();
const username = ref('');
const password = ref('');
const submitting = ref(false);
const errorMessage = ref('');
const visible = computed(() => !authStore.isAuthenticated);

async function submit() {
  errorMessage.value = '';
  if (!username.value.trim() || !password.value) {
    errorMessage.value = '请输入用户名和密码。';
    return;
  }
  submitting.value = true;
  try {
    const session = await gateway.login?.(username.value.trim(), password.value);
    if (!session) throw new Error('网关未返回有效会话。');
    authStore.setSession(session);
    appStore.pushNotice({ level: session.mustChangePassword || session.bootstrap ? 'WARN' : 'INFO', title: session.mustChangePassword || session.bootstrap ? '已使用引导管理员登录' : '登录成功', message: session.mustChangePassword || session.bootstrap ? '当前账号来自首次启动生成的引导管理员，必须尽快修改密码并迁移为正式账号。' : `欢迎，${session.displayName}。` });
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '登录失败';
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div v-if="visible" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/90 backdrop-blur-sm">
    <div class="w-full max-w-md rounded-3xl border border-slate-700 bg-slate-900 p-6 shadow-2xl">
      <div class="mb-4">
        <h2 class="text-xl font-semibold text-white">登录 HMI 网关</h2>
        <p class="mt-2 text-sm text-slate-300">系统已禁用默认自动登录。请使用已配置账号，或在首次启动后查看运行目录中的 bootstrap 管理员文件。</p>
      </div>
      <form class="space-y-4" @submit.prevent="submit">
        <label class="block text-sm text-slate-200"><span class="mb-1 block">用户名</span><input v-model="username" autocomplete="username" class="w-full rounded-2xl border border-slate-700 bg-slate-950 px-4 py-3 text-white outline-none ring-0" /></label>
        <label class="block text-sm text-slate-200"><span class="mb-1 block">密码</span><input v-model="password" type="password" autocomplete="current-password" class="w-full rounded-2xl border border-slate-700 bg-slate-950 px-4 py-3 text-white outline-none ring-0" /></label>
        <p v-if="errorMessage" class="rounded-2xl border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">{{ errorMessage }}</p>
        <button :disabled="submitting" class="w-full rounded-2xl bg-sky-600 px-4 py-3 text-sm font-medium text-white transition hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-60">{{ submitting ? '登录中…' : '登录并进入系统' }}</button>
      </form>
    </div>
  </div>
</template>
