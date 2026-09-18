<script setup>
import { onMounted, ref } from 'vue'
import { getJSON, postJSON } from '../api'
import TierLadder from '../components/TierLadder.vue'
import SegmentTable from '../components/SegmentTable.vue'

const accounts = ref([])
const accountId = ref(null)
const period = ref('2026-09')
const kwh = ref(220)
const peak = ref(false)
const result = ref(null)
const error = ref('')

onMounted(async () => {
  accounts.value = (await getJSON('/api/accounts')).items
})

async function pickAccount() {
  result.value = null
  if (!accountId.value) return
  // 以该户最近抄表电量作为毛电量预填
  const r = await getJSON(`/api/accounts/${accountId.value}`)
  if (r.readings[0]) kwh.value = r.readings[0].kwh
}

async function run(persist) {
  error.value = ''
  try {
    result.value = await postJSON('/api/bill', {
      kwh: kwh.value,
      peak: peak.value,
      account_id: accountId.value || null,
      period: accountId.value ? period.value : null,
      persist,
    })
  } catch (e) {
    error.value = e.message
  }
}
</script>
<template>
  <div class="page work">
    <h1>测算工作台</h1>
    <div class="panel form-row">
      <label>户号
        <select v-model="accountId" @change="pickAccount">
          <option :value="null">（不关联户号）</option>
          <option v-for="a in accounts" :key="a.id" :value="a.id">{{ a.name }} · {{ a.meter_no }}</option>
        </select>
      </label>
      <label v-if="accountId">账期 <input type="month" v-model="period" /></label>
      <label>毛电量(kWh) <input type="number" v-model.number="kwh" min="0" step="1" /></label>
      <label><input type="checkbox" v-model="peak" /> 尖峰系数</label>
      <button class="btn-trial" @click="run(false)">试算（不入库）</button>
      <button @click="run(true)">计算并入库</button>
    </div>
    <p v-if="error" class="err">⚠ {{ error }}</p>
    <div v-if="result" class="panel">
      <div class="credit-strip">
        <span>毛电量 <strong>{{ result.gross_kwh }}</strong></span>
        <span v-if="result.credit && result.credit.deducted > 0">
          信用扣除 <strong class="deduct">−{{ result.credit.deducted }}</strong>
        </span>
        <span>净电量 <strong class="net">{{ result.net_kwh }}</strong></span>
        <span>合计 <strong>¥{{ result.total }}</strong></span>
        <span v-if="result.run_id" class="muted">记录#{{ result.run_id }}</span>
      </div>
      <p v-if="result.credit && result.credit.deducted > 0" class="muted">
        账期 {{ result.credit.period }} 有效信用 {{ result.credit.total }} kWh 已在分段前扣除；作废后再次试算净电量将回升。
      </p>
      <TierLadder :segments="result.segments" />
      <SegmentTable :rows="result.segments" />
    </div>
  </div>
</template>
<style scoped>
.form-row { display: flex; flex-wrap: wrap; gap: 1rem; align-items: end; }
input[type=number] { width: 6rem; margin-left: 0.35rem; }
select { background: #0d1612; border: 1px solid var(--muted); color: var(--text); padding: 0.35rem 0.5rem; border-radius: 6px; }
.credit-strip { display: flex; flex-wrap: wrap; gap: 1.5rem; align-items: baseline; font-size: 1.05rem; margin-bottom: 0.5rem; }
.deduct { color: #ffb27a; }
.net { color: var(--accent); }
.err { color: #ff9d9d; padding: 0 1.25rem; }
.btn-trial { background: transparent; border: 1px solid var(--accent); color: var(--accent); }
</style>
