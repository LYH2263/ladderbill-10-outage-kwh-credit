<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { errorMessage, getJSON, postJSON } from '../api'
import TierLadder from '../components/TierLadder.vue'
import SegmentTable from '../components/SegmentTable.vue'

const accounts = ref([])
const accountId = ref(null)
const accountDetail = ref(null)
const period = ref('')
const kwh = ref(220)
const peak = ref(false)
const result = ref(null)
const err = ref('')
const savedRunId = ref(null)

const periods = computed(() => {
  const ps = (accountDetail.value?.readings || []).map(r => r.period).filter(Boolean)
  return [...new Set(ps)].sort().reverse()
})

async function loadAccounts() {
  accounts.value = (await getJSON('/api/accounts')).items
  if (!accountId.value && accounts.value.length) accountId.value = accounts.value[0].id
}

async function loadAccountDetail() {
  accountDetail.value = accountId.value
    ? await getJSON(`/api/accounts/${accountId.value}`)
    : null
  const ps = periods.value
  period.value = ps[0] || ''
}

watch(accountId, loadAccountDetail)
watch(period, p => {
  const reading = (accountDetail.value?.readings || []).find(r => r.period === p)
  if (reading) peak.value = !!reading.peak
})

async function calc(persist) {
  err.value = ''
  result.value = null
  savedRunId.value = null
  const body = { peak: peak.value, persist }
  if (accountId.value && period.value) {
    body.account_id = accountId.value
    body.period = period.value
  } else {
    body.kwh = Number(kwh.value)
  }
  try {
    result.value = await postJSON('/api/bill', body)
    if (persist) savedRunId.value = result.value.run_id
  } catch (e) {
    err.value = errorMessage(e)
  }
}

onMounted(loadAccounts)
</script>
<template>
  <div class="page work">
    <h1>测算工作台</h1>
    <div class="panel form-row">
      <label>户号
        <select v-model="accountId">
          <option v-for="a in accounts" :key="a.id" :value="a.id">{{ a.name }}（{{ a.meter_no }}）</option>
        </select>
      </label>
      <label v-if="periods.length">账期
        <select v-model="period">
          <option v-for="p in periods" :key="p" :value="p">{{ p }}</option>
        </select>
      </label>
      <label v-if="!periods.length">
        电量(kWh) <input type="number" v-model.number="kwh" min="0" step="1" style="width:6rem;margin-left:.35rem" />
      </label>
      <label><input type="checkbox" v-model="peak" /> 尖峰系数</label>
      <button class="btn-preview" @click="calc(false)">试算（不入库）</button>
      <button @click="calc(true)">计算并入库</button>
    </div>

    <p v-if="periods.length" class="muted">
      按户账期测算：以「毛电量 − 有效停电信用合计」得到的净电量参与分段与尖峰；信用以户详情页维护，作废后立即回升。
    </p>
    <p v-if="err" class="error">⛔ {{ err }}</p>

    <div v-if="result" class="panel">
      <div v-if="result.period" class="deduct">
        <span>毛电量 <strong>{{ result.gross_kwh }}</strong></span>
        <span class="arrow">−</span>
        <span>有效信用扣除 <strong class="credit-num">{{ result.credit_kwh }}</strong></span>
        <span class="arrow">=</span>
        <span>净电量 <strong class="hero-num" style="font-size:1.6rem">{{ result.net_kwh }}</strong> kWh</span>
      </div>
      <p class="muted" v-if="result.credits && result.credits.length">
        参与扣除：<span v-for="c in result.credits" :key="c.id" class="chip">#{{ c.id }} × {{ c.kwh }}kWh</span>
      </p>
      <p>
        合计 <strong class="hero-num" style="font-size:1.8rem">¥{{ result.total }}</strong>
        <span v-if="savedRunId" class="muted"> 已入库 · 记录#{{ savedRunId }}</span>
        <span v-else class="muted"> 试算结果，未写入运行记录</span>
      </p>
      <TierLadder :segments="result.segments" />
      <SegmentTable :rows="result.segments" />
    </div>
  </div>
</template>
<style scoped>
.form-row { display: flex; flex-wrap: wrap; gap: 1rem; align-items: end; }
select { background: #0d1612; border: 1px solid var(--muted); color: var(--text); padding: 0.35rem 0.5rem; border-radius: 6px; }
.btn-preview { background: transparent; border: 1px solid var(--accent); color: var(--accent); }
.deduct { display: flex; flex-wrap: wrap; gap: 0.8rem; align-items: baseline; font-size: 1.05rem; margin-bottom: 0.4rem; }
.credit-num { color: #e8b34b; font-size: 1.2rem; }
.arrow { color: var(--muted); }
.chip { display: inline-block; margin-right: 0.4rem; padding: 0.05rem 0.45rem; border-radius: 999px; background: color-mix(in srgb, #e8b34b 16%, transparent); font-size: 0.8rem; }
.error { color: #ff8a80; }
</style>
