document.getElementById('send-button').addEventListener('click', sendMessage);
document.getElementById('user-input').addEventListener('keypress', function(event) {
    if (event.key === 'Enter' && !event.ctrlKey) {
        sendMessage();
    }
});

document.getElementById('user-input').addEventListener('keydown', function(event) {
    if (event.key === 'Enter' && event.ctrlKey) {
        event.preventDefault(); // Prevent the default action
        insertNewlineAtCursor(this);
    }
});

function insertNewlineAtCursor(input) {
    const start = input.selectionStart;
    const end = input.selectionEnd;
    const value = input.value;

    // Insert a newline character at the cursor position
    input.value = value.substring(0, start) + '\n' + value.substring(end);

    // Move the cursor to the position after the newline
    input.selectionStart = input.selectionEnd = start + 1;
}

function sendMessage() {
    const userInput = document.getElementById('user-input').value.trim();
    if (!userInput.trim()) {
        alert('请输入内容');
        return;
    }

    // Display user's message
    const chatLog = document.getElementById('chat-log');
    const userMessage = document.createElement('div');
    userMessage.className = 'user-message';
    userMessage.innerHTML = `<img src="/static/user_logo.png" alt="User"><div class="text">${userInput}</div>`;
    chatLog.appendChild(userMessage);

    // Display thinking message
    const assistantMessage = document.createElement('div');
    assistantMessage.className = 'assistant-message';
    assistantMessage.innerHTML = `<img src="/static/assistant_logo.png" alt="Assistant"><div class="text">正在思考中...</div>`;
    chatLog.appendChild(assistantMessage);

    // Scroll to the bottom
    chatLog.scrollTop = chatLog.scrollHeight;

    // Send the question to the server
    fetch('/ask', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ question: userInput })
    })
    .then(response => response.json())
    .then(data => {
        console.log('Answer:', data.answer); // Log the answer for debugging
        try {
            // Render markdown and update the assistant's message
            assistantMessage.querySelector('.text').innerHTML = marked.parse(data.answer);
        } catch (error) {
            console.error('Markdown rendering error:', error);
            assistantMessage.querySelector('.text').innerHTML = 'Markdown rendering error';
        }
    })
    .catch(error => {
        console.error('Error:', error);
        assistantMessage.querySelector('.text').innerHTML = '内部错误';
    });

    // Clear the input field
    document.getElementById('user-input').value = '';
}

// Add event listener to chat log for link clicks
document.getElementById('chat-log').addEventListener('click', async function(event) {
    if (event.target.tagName === 'A') {
        event.preventDefault(); // Prevent the default link behavior
        const url = event.target.href;
        const filename = event.target.textContent;

        // Create an anchor element and trigger a download
        const anchor = document.createElement('a');
        anchor.href = url;
        anchor.download = filename;
        document.body.appendChild(anchor);
        anchor.click();
        document.body.removeChild(anchor);
    }
});

// Sidebar resizing
const sidebar = document.querySelector('.sidebar');
const resizeHandle = document.querySelector('.resize-handle');
const chatArea = document.querySelector('.chat-area');

let isResizing = false;
let lastX;

resizeHandle.addEventListener('mousedown', (e) => {
    isResizing = true;
    lastX = e.clientX;
    document.body.style.cursor = 'col-resize'; // Change cursor during resizing
});

document.addEventListener('mousemove', (e) => {
    if (!isResizing) return;
    const dx = e.clientX - lastX;
    const newWidth = sidebar.offsetWidth + dx;
    sidebar.style.width = `${newWidth}px`;
    chatArea.style.width = `calc(100% - ${newWidth}px)`;
    lastX = e.clientX;
});

document.addEventListener('mouseup', () => {
    isResizing = false;
    document.body.style.cursor = ''; // Reset cursor after resizing
});

document.addEventListener('DOMContentLoaded', function() {
    const sidebar = document.querySelector('.sidebar');
    const resizeHandle = document.querySelector('.resize-handle');
    let isResizing = false;

    resizeHandle.addEventListener('mousedown', function(e) {
        isResizing = true;
        document.body.style.cursor = 'ew-resize';
    });

    document.addEventListener('mousemove', function(e) {
        if (!isResizing) return;
        const newWidth = e.clientX - sidebar.getBoundingClientRect().left;
        sidebar.style.width = `${newWidth}px`;
    });

    document.addEventListener('mouseup', function() {
        isResizing = false;
        document.body.style.cursor = 'default';
    });
});

// Add event listener to upload button
document.getElementById('upload-button').addEventListener('click', function() {
    document.getElementById('file-input').click();
});

// Add event listener to file input
document.getElementById('file-input').addEventListener('change', function(event) {
    const file = event.target.files[0];
    if (file) {
        const formData = new FormData();
        formData.append('file', file);

        fetch('/upload', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert('文件上传成功');
            } else {
                alert('文件上传失败');
            }
        })
        .catch(error => {
            console.error('Error uploading file:', error);
            alert('文件上传失败');
        });
    }
});

const socket = io.connect('http://' + document.domain + ':' + location.port);

// Listen for 'doc_content' events from the server
socket.on('doc_content', function(data) {
    const chatLog = document.getElementById('chat-log');
    const assistantMessage = document.createElement('div');
    assistantMessage.className = 'assistant-message';
    assistantMessage.innerHTML = `<img src="/static/assistant_logo.png" alt="Assistant"><div class="text">${data.content}</div>`;
    chatLog.appendChild(assistantMessage);

    // Scroll to the bottom
    chatLog.scrollTop = chatLog.scrollHeight;
});

