// PandasDB CRM Backoffice JavaScript

class BackofficeApp {
    constructor() {
        this.apiBaseUrl = this.getApiBaseUrl();
        this.init();
    }

    getApiBaseUrl() {
        // Try to get API URL from CloudFormation exports or fallback to constructed URL
        const hostname = window.location.hostname;
        
        // For local development
        if (hostname === 'localhost' || hostname === '127.0.0.1') {
            return 'https://your-api-gateway-id.execute-api.us-east-1.amazonaws.com/dev';
        }
        
        // For production, try to construct from current environment
        // This should be replaced with actual API Gateway URL during deployment
        return 'https://your-api-gateway-id.execute-api.us-east-1.amazonaws.com/dev';
    }

    init() {
        this.setupNavigation();
        this.setupSpamTabs();
        this.loadInitialData();
        this.setupEventListeners();
        
        // Set API endpoint in settings
        document.getElementById('apiEndpoint').value = this.apiBaseUrl;
    }

    setupNavigation() {
        const navItems = document.querySelectorAll('.nav-item');
        navItems.forEach(item => {
            item.addEventListener('click', (e) => {
                const tabName = e.target.dataset.tab;
                this.switchTab(tabName);
                
                // Update active nav item
                navItems.forEach(nav => nav.classList.remove('active'));
                e.target.classList.add('active');
            });
        });
    }

    setupSpamTabs() {
        const spamTabs = document.querySelectorAll('.spam-tab');
        spamTabs.forEach(tab => {
            tab.addEventListener('click', (e) => {
                const tabName = e.target.dataset.spamTab;
                this.switchSpamTab(tabName);
                
                // Update active spam tab
                spamTabs.forEach(t => t.classList.remove('active'));
                e.target.classList.add('active');
            });
        });
    }

    setupEventListeners() {
        // Enter key for lead search
        document.getElementById('leadSearchInput').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                this.searchLead();
            }
        });
    }

    switchTab(tabName) {
        // Hide all tabs
        document.querySelectorAll('.tab-content').forEach(tab => {
            tab.classList.remove('active');
        });
        
        // Show selected tab
        document.getElementById(tabName).classList.add('active');
        
        // Load tab-specific data
        switch(tabName) {
            case 'dashboard':
                this.loadDashboardData();
                break;
            case 'spam':
                this.loadSpamActivities();
                break;
        }
    }

    switchSpamTab(tabName) {
        // Hide all spam content
        document.querySelectorAll('.spam-content').forEach(content => {
            content.classList.remove('active');
        });
        
        // Show selected spam content
        document.getElementById(`spam-${tabName}`).classList.add('active');
        
        // Load appropriate data
        if (tabName === 'activities') {
            this.loadSpamActivities();
        } else if (tabName === 'users') {
            this.loadSpamUsers();
        }
    }

    async loadInitialData() {
        await this.loadDashboardData();
    }

    async loadDashboardData() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/api/analytics/daily`);
            const data = await response.json();
            
            if (response.ok) {
                this.updateDashboardStats(data);
                document.getElementById('lastUpdated').textContent = new Date(data.last_updated).toLocaleString();
            } else {
                this.showNotification('Failed to load dashboard data', 'error');
            }
        } catch (error) {
            this.showNotification('Error loading dashboard: ' + error.message, 'error');
        }
    }

    updateDashboardStats(data) {
        document.getElementById('totalLeads').textContent = data.total_leads.toLocaleString();
        document.getElementById('totalMessages').textContent = data.messages_today.toLocaleString();
        document.getElementById('spamPercentage').textContent = data.spam_percentage.toFixed(1) + '%';
        document.getElementById('spamUsers').textContent = data.spam_users.toLocaleString();
    }

    async refreshDashboard() {
        const refreshBtn = document.querySelector('[onclick="refreshDashboard()"]');
        const originalText = refreshBtn.innerHTML;
        refreshBtn.innerHTML = '<span class="refresh-icon">🔄</span> Refreshing...';
        refreshBtn.disabled = true;
        
        await this.loadDashboardData();
        
        setTimeout(() => {
            refreshBtn.innerHTML = originalText;
            refreshBtn.disabled = false;
        }, 1000);
    }

    async searchLead() {
        const leadId = document.getElementById('leadSearchInput').value.trim();
        if (!leadId) {
            this.showNotification('Please enter a lead ID', 'error');
            return;
        }

        try {
            document.getElementById('leadSearchResult').innerHTML = '<div class="loading">Searching lead...</div>';
            
            const response = await fetch(`${this.apiBaseUrl}/api/lead/${leadId}`);
            const data = await response.json();
            
            if (response.ok) {
                this.displayLeadResult(data);
            } else {
                document.getElementById('leadSearchResult').innerHTML = `<div class="error">Lead not found: ${data.error}</div>`;
            }
        } catch (error) {
            document.getElementById('leadSearchResult').innerHTML = `<div class="error">Error searching lead: ${error.message}</div>`;
        }
    }

    displayLeadResult(data) {
        const phoneContact = data.contact_methods.find(c => c.type === 'phone');
        const emailContact = data.contact_methods.find(c => c.type === 'email');
        
        const html = `
            <div class="section">
                <h3>👤 Lead Information</h3>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-bottom: 1rem;">
                    <div><strong>Name:</strong> ${data.lead.name}</div>
                    <div><strong>Created:</strong> ${new Date(data.lead.created_at).toLocaleString()}</div>
                    <div><strong>Phone:</strong> ${phoneContact?.value || 'N/A'}</div>
                    <div><strong>Email:</strong> ${emailContact?.value || 'N/A'}</div>
                </div>
                
                <h4>💬 Recent Messages (${data.activities.length})</h4>
                <div style="max-height: 400px; overflow-y: auto;">
                    <table class="table">
                        <thead>
                            <tr>
                                <th>Date</th>
                                <th>Direction</th>
                                <th>Message</th>
                                <th>Response</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${data.activities.map(activity => `
                                <tr>
                                    <td>${new Date(activity.created_at).toLocaleString()}</td>
                                    <td>
                                        <span style="padding: 0.25rem 0.5rem; border-radius: 12px; font-size: 0.8rem; 
                                              background: ${activity.direction === 'inbound' ? '#e3f2fd' : '#f3e5f5'}; 
                                              color: ${activity.direction === 'inbound' ? '#1976d2' : '#7b1fa2'};">
                                            ${activity.direction === 'inbound' ? '📥 In' : '📤 Out'}
                                        </span>
                                    </td>
                                    <td class="message-content" title="${activity.content?.leadMessage || 'N/A'}">
                                        ${activity.content?.leadMessage || 'N/A'}
                                    </td>
                                    <td class="message-content" title="${activity.content?.assistantMessage || 'N/A'}">
                                        ${activity.content?.assistantMessage || 'N/A'}
                                    </td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
        document.getElementById('leadSearchResult').innerHTML = html;
    }

    async loadSpamActivities() {
        try {
            document.getElementById('spamActivitiesList').innerHTML = '<div class="loading">Loading spam activities...</div>';
            
            const response = await fetch(`${this.apiBaseUrl}/api/spam/activities`);
            const data = await response.json();
            
            if (response.ok) {
                this.displaySpamActivities(data);
            } else {
                document.getElementById('spamActivitiesList').innerHTML = `<div class="error">Failed to load spam activities: ${data.error}</div>`;
            }
        } catch (error) {
            document.getElementById('spamActivitiesList').innerHTML = `<div class="error">Error loading spam activities: ${error.message}</div>`;
        }
    }

    displaySpamActivities(activities) {
        if (activities.length === 0) {
            document.getElementById('spamActivitiesList').innerHTML = '<div class="loading">No spam activities found in the last 7 days.</div>';
            return;
        }

        const html = `
            <table class="table">
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>Lead</th>
                        <th>Phone</th>
                        <th>Message</th>
                        <th>Reason</th>
                        <th>Flagged By</th>
                    </tr>
                </thead>
                <tbody>
                    ${activities.map(item => `
                        <tr class="spam-user">
                            <td>${new Date(item.spam_date).toLocaleString()}</td>
                            <td>${item.lead_name}</td>
                            <td>${item.phone}</td>
                            <td class="message-content" title="${item.message}">
                                ${item.message || 'N/A'}
                            </td>
                            <td>
                                <span style="padding: 0.25rem 0.5rem; border-radius: 12px; font-size: 0.8rem; 
                                      background: #ffebee; color: #c62828;">
                                    ${item.spam_reason}
                                </span>
                            </td>
                            <td>${item.flagged_by}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
        document.getElementById('spamActivitiesList').innerHTML = html;
    }

    async loadSpamUsers() {
        try {
            document.getElementById('spamUsersList').innerHTML = '<div class="loading">Loading spam users...</div>';
            
            const response = await fetch(`${this.apiBaseUrl}/api/spam/users`);
            const data = await response.json();
            
            if (response.ok) {
                this.displaySpamUsers(data);
            } else {
                document.getElementById('spamUsersList').innerHTML = `<div class="error">Failed to load spam users: ${data.error}</div>`;
            }
        } catch (error) {
            document.getElementById('spamUsersList').innerHTML = `<div class="error">Error loading spam users: ${error.message}</div>`;
        }
    }

    displaySpamUsers(users) {
        if (users.length === 0) {
            document.getElementById('spamUsersList').innerHTML = '<div class="loading">No spam users found in the last 30 days.</div>';
            return;
        }

        const html = `
            <table class="table">
                <thead>
                    <tr>
                        <th>Lead Name</th>
                        <th>Phone</th>
                        <th>Spam Count (30 days)</th>
                        <th>First Spam</th>
                        <th>Last Spam</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    ${users.map(user => `
                        <tr class="spam-user">
                            <td>${user.lead_name}</td>
                            <td>${user.phone}</td>
                            <td>
                                <span style="padding: 0.25rem 0.5rem; border-radius: 12px; font-size: 0.8rem; font-weight: bold;
                                      background: ${user.spam_count_30_days >= 5 ? '#ffcdd2' : '#fff3e0'}; 
                                      color: ${user.spam_count_30_days >= 5 ? '#d32f2f' : '#f57c00'};">
                                    ${user.spam_count_30_days}
                                </span>
                            </td>
                            <td>${user.first_spam ? new Date(user.first_spam).toLocaleDateString() : 'N/A'}</td>
                            <td>${user.last_spam ? new Date(user.last_spam).toLocaleDateString() : 'N/A'}</td>
                            <td>
                                <span style="padding: 0.25rem 0.5rem; border-radius: 12px; font-size: 0.8rem; font-weight: bold;
                                      background: ${user.is_blocked ? '#ffcdd2' : '#ffe0b2'}; 
                                      color: ${user.is_blocked ? '#d32f2f' : '#ef6c00'};">
                                    ${user.is_blocked ? '🚫 Blocked' : '⚠️ Warning'}
                                </span>
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
        document.getElementById('spamUsersList').innerHTML = html;
    }

    showNotification(message, type = 'info') {
        const notification = document.createElement('div');
        notification.className = `notification ${type}`;
        notification.textContent = message;
        
        document.getElementById('notifications').appendChild(notification);
        
        setTimeout(() => {
            notification.remove();
        }, 5000);
    }

    exportData(type) {
        this.showNotification(`Exporting ${type} data...`, 'info');
        // TODO: Implement data export functionality
        setTimeout(() => {
            this.showNotification(`${type} data export completed!`, 'success');
        }, 2000);
    }
}

// Global functions for onclick handlers
let app;

window.onload = function() {
    app = new BackofficeApp();
};

function refreshDashboard() {
    app.refreshDashboard();
}

function searchLead() {
    app.searchLead();
}

function loadSpamActivities() {
    app.loadSpamActivities();
}

function loadSpamUsers() {
    app.loadSpamUsers();
}

function exportData(type) {
    app.exportData(type);
}
