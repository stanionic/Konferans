const socket = io();
let localStream;
let peers = {};
let mediaRecorder;
let recordedChunks = [];

function initRoom(roomId) {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        alert('Your browser does not support camera and microphone access. Please use a modern browser.');
        return;
    }
    navigator.mediaDevices.getUserMedia({ video: true, audio: true }).then(stream => {
        localStream = stream;
        document.getElementById('localVideo').srcObject = stream;

        const peer = new Peer(undefined, {
            host: 'peerjs.com',
            secure: true,
            port: 443
        });

        peer.on('open', id => {
            socket.emit('join', { room: roomId, username: socket.id, peerId: id });
        });

        peer.on('call', call => {
            call.answer(localStream);
            call.on('stream', remoteStream => {
                addVideoStream(call.peer, remoteStream);
            });
            call.on('error', err => {
                console.error('Call error:', err);
            });
        });

        peer.on('error', err => {
            console.error('Peer error:', err);
            alert('PeerJS error: ' + err.message);
        });

        socket.on('user_joined', data => {
            connectToNewUser(data.peerId, localStream, peer, roomId);
        });

        socket.on('user_left', data => {
            if (peers[data.peerId]) {
                peers[data.peerId].close();
                delete peers[data.peerId];
                removeVideoStream(data.peerId);
            }
        });

        socket.on('warning', data => {
            showWarning(data.message);
        });

        socket.on('error', data => {
            showError(data.message);
        });
    }).catch(err => {
        console.error('Error accessing media devices:', err);
        alert('Error accessing camera and microphone: ' + err.message + '. Please allow permissions and try again.');
    });

    // Mute/Unmute button
    document.getElementById('muteBtn').addEventListener('click', () => {
        if (!localStream) {
            alert('Camera and microphone not available. Please allow permissions and refresh the page.');
            return;
        }
        const audioTracks = localStream.getAudioTracks()[0];
        if (audioTracks) {
            audioTracks.enabled = !audioTracks.enabled;
            document.getElementById('muteBtn').innerHTML = audioTracks.enabled ? '<i class="fas fa-microphone"></i>' : '<i class="fas fa-microphone-slash"></i>';
        }
    });

    // Video on/off button
    document.getElementById('videoBtn').addEventListener('click', () => {
        if (!localStream) {
            alert('Camera and microphone not available. Please allow permissions and refresh the page.');
            return;
        }
        const videoTracks = localStream.getVideoTracks()[0];
        if (videoTracks) {
            videoTracks.enabled = !videoTracks.enabled;
            document.getElementById('videoBtn').innerHTML = videoTracks.enabled ? '<i class="fas fa-video"></i>' : '<i class="fas fa-video-slash"></i>';
        }
    });

    // Record button
    document.getElementById('recordBtn').addEventListener('click', () => {
        if (!localStream) {
            alert('Camera and microphone not available. Please allow permissions and refresh the page.');
            return;
        }
        if (mediaRecorder && mediaRecorder.state === 'recording') {
            stopRecording();
        } else {
            startRecording();
        }
    });

    // Leave room button
    document.getElementById('leaveBtn').addEventListener('click', () => {
        if (localStream) {
            localStream.getTracks().forEach(track => track.stop());
        }
        Object.values(peers).forEach(call => call.close());
        socket.emit('leave', { room: roomId, username: socket.id || 'user' });
        window.location.href = '/';
    });
}

function connectToNewUser(userId, stream, peer, roomId) {
    const call = peer.call(userId, stream);
    call.on('stream', remoteStream => {
        addVideoStream(userId, remoteStream);
    });
    call.on('close', () => {
        removeVideoStream(userId);
    });
    peers[userId] = call;
}

function addVideoStream(userId, stream) {
    const video = document.createElement('video');
    video.srcObject = stream;
    video.id = userId;
    video.autoplay = true;
    document.getElementById('videos').appendChild(video);
    updateUserList();
}

function removeVideoStream(userId) {
    const video = document.getElementById(userId);
    if (video) {
        video.remove();
    }
    updateUserList();
}

function updateUserList() {
    const usersDiv = document.getElementById('users');
    const videos = document.querySelectorAll('#videos video');
    usersDiv.innerHTML = '<h3>Users in room:</h3><ul>' + Array.from(videos).map(video => `<li>${video.id}</li>`).join('') + '</ul>';
}

function startRecording() {
    recordedChunks = [];
    mediaRecorder = new MediaRecorder(localStream);
    mediaRecorder.ondataavailable = event => {
        if (event.data.size > 0) {
            recordedChunks.push(event.data);
        }
    };
    mediaRecorder.onstop = () => {
        const blob = new Blob(recordedChunks, { type: 'video/webm' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'conference_recording.webm';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    };
    mediaRecorder.start();
    document.getElementById('recordBtn').innerHTML = '<i class="fas fa-stop"></i>';
}

function stopRecording() {
    if (mediaRecorder && mediaRecorder.state === 'recording') {
        mediaRecorder.stop();
        document.getElementById('recordBtn').innerHTML = '<i class="fas fa-record-vinyl"></i>';
    }
}
