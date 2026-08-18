import { useQuery } from '@tanstack/react-query'
import { Settings as SettingsIcon, CheckCircle, XCircle, AlertCircle } from 'lucide-react'
import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface Settings {
  llm_model: string
  llm_base_url: string
  llm_temperature: number
  llm_max_tokens: number
  cors_origins: string
  environment: string
  vt_enabled: boolean
  abuseipdb_enabled: boolean
  shodan_enabled: boolean
  rules_dir: string
  log_level: string
}

export default function Settings() {
  const { data: settings, isLoading, error } = useQuery<Settings>({
    queryKey: ['settings'],
    queryFn: async () => {
      const response = await axios.get(`${API_URL}/api/v1/settings`)
      return response.data
    },
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-400">Loading settings...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="space-y-8">
        <div>
          <h2 className="text-3xl font-bold mb-2">Settings</h2>
          <p className="text-gray-400">Configure Sentinel</p>
        </div>
        <div className="bg-red-500/10 border border-red-500 rounded-lg p-6">
          <div className="flex items-start space-x-3">
            <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
            <div>
              <h4 className="font-medium text-red-500">Failed to load settings</h4>
              <p className="text-sm text-red-400">Please check API connection and authentication.</p>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-3xl font-bold mb-2">Settings</h2>
        <p className="text-gray-400">Configure Sentinel</p>
      </div>

      {/* LLM Configuration */}
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <h3 className="text-xl font-bold mb-4 flex items-center">
          <SettingsIcon className="w-5 h-5 mr-2" />
          LLM Configuration
        </h3>
        <div className="space-y-4">
          <div>
            <label className="text-sm text-gray-400">Model</label>
            <p className="text-lg font-medium">{settings?.llm_model}</p>
          </div>
          <div>
            <label className="text-sm text-gray-400">Base URL</label>
            <p className="text-lg font-medium break-all">{settings?.llm_base_url}</p>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm text-gray-400">Temperature</label>
              <p className="text-lg font-medium">{settings?.llm_temperature}</p>
            </div>
            <div>
              <label className="text-sm text-gray-400">Max Tokens</label>
              <p className="text-lg font-medium">{settings?.llm_max_tokens}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Threat Intelligence */}
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <h3 className="text-xl font-bold mb-4">Threat Intelligence</h3>
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-gray-300">VirusTotal</span>
            <span className={`flex items-center space-x-2 ${settings?.vt_enabled ? 'text-green-400' : 'text-gray-500'}`}>
              {settings?.vt_enabled ? <CheckCircle className="w-5 h-5" /> : <XCircle className="w-5 h-5" />}
              <span>{settings?.vt_enabled ? 'Enabled' : 'Disabled'}</span>
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-gray-300">AbuseIPDB</span>
            <span className={`flex items-center space-x-2 ${settings?.abuseipdb_enabled ? 'text-green-400' : 'text-gray-500'}`}>
              {settings?.abuseipdb_enabled ? <CheckCircle className="w-5 h-5" /> : <XCircle className="w-5 h-5" />}
              <span>{settings?.abuseipdb_enabled ? 'Enabled' : 'Disabled'}</span>
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-gray-300">Shodan</span>
            <span className={`flex items-center space-x-2 ${settings?.shodan_enabled ? 'text-green-400' : 'text-gray-500'}`}>
              {settings?.shodan_enabled ? <CheckCircle className="w-5 h-5" /> : <XCircle className="w-5 h-5" />}
              <span>{settings?.shodan_enabled ? 'Enabled' : 'Disabled'}</span>
            </span>
          </div>
        </div>
        <div className="mt-4 p-3 bg-blue-500/10 border border-blue-500/30 rounded text-sm text-blue-400">
          <p>ℹ️ API keys are configured via environment variables and require service restart to change.</p>
        </div>
      </div>

      {/* System Configuration */}
      <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <h3 className="text-xl font-bold mb-4">System Configuration</h3>
        <div className="space-y-4">
          <div>
            <label className="text-sm text-gray-400">Environment</label>
            <p className="text-lg font-medium">
              <span className={`px-3 py-1 rounded-full text-sm ${
                settings?.environment === 'production'
                  ? 'bg-red-500/20 text-red-400'
                  : 'bg-yellow-500/20 text-yellow-400'
              }`}>
                {settings?.environment}
              </span>
            </p>
          </div>
          <div>
            <label className="text-sm text-gray-400">CORS Origins</label>
            <p className="text-lg font-medium break-all">{settings?.cors_origins}</p>
          </div>
          <div>
            <label className="text-sm text-gray-400">Rules Directory</label>
            <p className="text-lg font-medium">{settings?.rules_dir}</p>
          </div>
          <div>
            <label className="text-sm text-gray-400">Log Level</label>
            <p className="text-lg font-medium">{settings?.log_level}</p>
          </div>
        </div>
      </div>

      {/* Security Notice */}
      <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-4">
        <h4 className="font-medium text-yellow-400 mb-2">🔒 Security Note</h4>
        <p className="text-sm text-yellow-300">
          API keys and sensitive configuration are managed via environment variables only.
          They are never exposed through this interface or stored in the database.
        </p>
      </div>
    </div>
  )
}
