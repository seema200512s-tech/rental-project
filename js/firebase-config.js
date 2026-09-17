// js/firebase-config.js
// Firebase CDN compat scripts must be loaded BEFORE this file in each HTML page.

const firebaseConfig = {
    apiKey: "AIzaSyDRPmc3Xaolv6L0htEBHT_oSXVIun_-IdM",
    authDomain: "rental-a23e8.firebaseapp.com",
    databaseURL: "https://rental-a23e8-default-rtdb.firebaseio.com",
    projectId: "rental-a23e8",
    storageBucket: "rental-a23e8.firebasestorage.app",
    messagingSenderId: "216485240005",
    appId: "1:216485240005:web:a5a2f418c0e3377e6664ac",
    measurementId: "G-YJRK5S0ZM5"
};

// Initialize Firebase
if (!firebase.apps.length) {
    firebase.initializeApp(firebaseConfig);
}

const auth = firebase.auth();
const database = firebase.database();
const storage = firebase.storage();
